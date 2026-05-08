from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

from app.core.enums import ImageStatus, OrderStatus
from app.core.models import Order, OrderImage
from app.core.order_service import OrderService, order_service
from app.notifiers.telegram_notifier import TelegramNotifierError, build_telegram_notifier
from app.storage.database import init_db
from app.storage.file_store import FileStore, file_store
from config.paths import ProjectPaths, get_project_paths
from config.settings import Settings, get_settings


@dataclass
class EditedWatcherResult:
    """
    单次人工修图回流处理结果。
    """

    order_id: str
    edited_file: Path
    image_id: str | None = None
    success: bool = False
    error: str | None = None


class EditedWatcher:
    """
        edited 成图回流监听 worker。

        当前工作流：

        1. incoming 收到买家原图
        2. folder_watcher 创建订单，并把原图放入 original/
        3. 图片处理完成后，成图被放入：

            data/orders/{order_id}/edited/

        4. edited_watcher 自动发现 edited 里的新图
        5. 绑定到订单图片
        6. 从 edited 生成带水印 preview
        7. Telegram 通知你审核 preview

        edited/ 里的图片来源可以是：

        - local 模式下你手动修好的图
        - with_api 模式下 API 生成的图
        - 以后其他处理后端生成的图

        核心规则：

        - edited/ 只放真正处理完成的成图
        - preview/ 只能从 edited/ 生成
        - 不再从 original/ 兜底生成 preview
        """

    def __init__(
        self,
        service: OrderService | None = None,
        store: FileStore | None = None,
        paths: ProjectPaths | None = None,
        settings: Settings | None = None,
        notify_telegram: bool = True,
    ) -> None:
        self.service = service or order_service
        self.store = store or file_store
        self.paths = paths or get_project_paths()
        self.settings = settings or get_settings()
        self.notify_telegram = notify_telegram
        self._running = False

        # 避免同一轮运行中重复处理同一个文件
        self._seen_files: set[str] = set()

    def run_once(self) -> list[EditedWatcherResult]:
        """
        扫描所有可能等待 edited 回流的订单。

        适合调试：

            python -m app.workers.edited_watcher
        """
        init_db()

        orders = self._load_candidate_orders()
        results: list[EditedWatcherResult] = []

        for order in orders:
            edited_files = self._discover_manual_edited_files(order)

            for edited_file in edited_files:
                result = self._handle_edited_file(order, edited_file)
                results.append(result)

        if not results:
            logger.debug("No manual edited files found")

        return results

    def run_forever(self) -> None:
        """
        持续监听所有订单的 edited 目录。
        """
        init_db()
        self._running = True

        logger.info("Edited watcher started")
        logger.info(f"Orders directory: {self.paths.orders_dir}")
        logger.info(f"Watch interval: {self.settings.watch_interval_seconds}s")
        logger.info(f"Telegram notification: {self.notify_telegram}")

        try:
            while self._running:
                self.run_once()
                time.sleep(self.settings.watch_interval_seconds)
        except KeyboardInterrupt:
            logger.info("Edited watcher stopped by keyboard interrupt")
        finally:
            self._running = False
            logger.info("Edited watcher stopped")

    def stop(self) -> None:
        self._running = False

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def _load_candidate_orders(self) -> list[Order]:
        """
        找出可能正在等待 edited 成图的订单。

        主要包含：

        - IMAGES_RECEIVED：local 模式下刚收图，等待你手动修
        - PROCESSING：审核打回后，等待重新处理
        - WAITING_FOR_REVIEW：允许重新放 edited 覆盖生成新 preview
        - FAILED：允许人工补救
        """
        statuses = [
            OrderStatus.IMAGES_RECEIVED,
            OrderStatus.PROCESSING,
            OrderStatus.WAITING_FOR_REVIEW,
            OrderStatus.FAILED,
        ]

        orders: list[Order] = []

        for status in statuses:
            orders.extend(self.service.list_orders(status=status, limit=300))

        unique: dict[str, Order] = {order.order_id: order for order in orders}
        return list(unique.values())

    def _discover_manual_edited_files(self, order: Order) -> list[Path]:
        """
        扫描某个订单 edited/ 目录中的新成图。
        """
        edited_dir = self.paths.edited_dir(order.order_id)

        if not edited_dir.exists():
            return []

        known_paths = {
            image.edited_path.resolve().as_posix()
            for image in order.images
            if image.edited_path is not None and image.edited_path.exists()
        }

        files: list[Path] = []

        for path in edited_dir.iterdir():
            if not path.is_file():
                continue

            if not self.paths.is_supported_image(path):
                continue

            resolved = path.resolve().as_posix()

            # 已经绑定到订单图片的 edited_path，不重复处理
            if resolved in known_paths:
                continue

            # 当前 watcher 运行期间已经处理过的，也不重复处理
            if resolved in self._seen_files:
                continue

            # 跳过明显的临时文件
            if path.name.startswith("~") or path.name.startswith("."):
                continue

            files.append(path)

        files.sort(key=lambda item: item.stat().st_mtime)
        return files

    # ------------------------------------------------------------------
    # Handling
    # ------------------------------------------------------------------

    def _handle_edited_file(self, order: Order, edited_file: Path) -> EditedWatcherResult:
        result = EditedWatcherResult(
            order_id=order.order_id,
            edited_file=edited_file,
        )

        try:
            logger.info(f"Handling manual edited file: {edited_file}")

            if not self.store.wait_until_file_stable(edited_file):
                raise RuntimeError(f"File is not stable or timed out: {edited_file}")

            image = self._match_image(order, edited_file)

            if image is None:
                raise RuntimeError(
                    f"Could not match edited file to any image in order {order.order_id}: "
                    f"{edited_file.name}"
                )

            # 关键点：
            # 这里不再复制 original，不再自动生成 edited。
            # 你放进 edited/ 的文件，就是真正的处理完成图。
            image.mark_edited(edited_file)

            # 先保存 edited_path，再让 order_service 从 edited_path 生成 preview
            self.service.repository.save_order(order)
            self.service.store.save_order_metadata(order)

            refreshed_order = self.service.generate_previews(order.order_id)

            result.image_id = image.image_id
            result.success = True
            self._seen_files.add(edited_file.resolve().as_posix())

            logger.info(
                f"Generated preview from edited file: "
                f"order={order.order_id}, image={image.image_id}, file={edited_file.name}"
            )

            if self.notify_telegram:
                self._notify_review_if_possible(refreshed_order)

            return result

        except Exception as exc:
            logger.exception(f"Failed to handle manual edited file: {edited_file}")

            result.success = False
            result.error = str(exc)

            self._seen_files.add(edited_file.resolve().as_posix())
            self._write_error_file(edited_file, exc)

            return result

    def _match_image(self, order: Order, edited_file: Path) -> OrderImage | None:
        """
        将 edited/ 里的成图匹配到订单中的某张原图。

        匹配优先级：

        1. 完整文件名匹配
           original: image.jpg
           edited:   image.jpg

        2. 文件 stem 匹配
           original: image.jpg
           edited:   image.png

        3. 第一张还没有 edited_path 的图片

        4. 第一张处于待处理 / 重做 / 失败状态的图片

        5. 如果订单只有一张图，直接匹配
        """
        edited_name = edited_file.name.lower()
        edited_stem = edited_file.stem.lower()

        # 1. 完整文件名匹配
        for image in order.images:
            if image.filename.lower() == edited_name:
                return image

        # 2. 文件 stem 匹配
        for image in order.images:
            if Path(image.filename).stem.lower() == edited_stem:
                return image

        # 3. 优先匹配还没有 edited_path 的图片
        for image in order.images:
            if image.edited_path is None:
                return image

        # 4. 匹配处于待处理 / 被拒绝 / 失败状态的图片
        for image in order.images:
            if image.status in {
                ImageStatus.RECEIVED,
                ImageStatus.EDITING,
                ImageStatus.REJECTED,
                ImageStatus.FAILED,
            }:
                return image

        # 5. 单图订单兜底
        if len(order.images) == 1:
            return order.images[0]

        return None

    def _write_error_file(self, edited_file: Path, error: Exception) -> None:
        """
        处理失败时，在 edited 图旁边写一个错误说明文件。
        """
        error_path = edited_file.with_suffix(edited_file.suffix + ".watcher_error.txt")
        error_path.write_text(str(error), encoding="utf-8")

    def _notify_review_if_possible(self, order: Order) -> None:
        """
        preview 已经生成，通知 Telegram 进入审核阶段。
        """
        if not self.settings.telegram_bot_token or self.settings.telegram_admin_user_id is None:
            logger.warning(
                "Telegram is not configured. Skipped edited watcher review notification."
            )
            return

        try:
            notifier = build_telegram_notifier()
            notifier.notify_order_ready_for_review(order)
            logger.info(f"Sent Telegram review notification for edited file: {order.order_id}")
        except TelegramNotifierError:
            logger.exception("Failed to send Telegram review notification")
        except Exception:
            logger.exception("Unexpected error while sending Telegram notification")


def build_edited_watcher(notify_telegram: bool = True) -> EditedWatcher:
    return EditedWatcher(notify_telegram=notify_telegram)


def run_edited_watcher(
    once: bool = False,
    notify_telegram: bool = True,
) -> list[EditedWatcherResult] | None:
    watcher = build_edited_watcher(notify_telegram=notify_telegram)

    if once:
        return watcher.run_once()

    watcher.run_forever()
    return None


if __name__ == "__main__":
    run_edited_watcher(once=False)