from __future__ import annotations

import time
from dataclasses import dataclass

from loguru import logger

from app.core.enums import OrderStatus
from app.core.models import Order
from app.core.order_service import OrderService, order_service
from app.notifiers.telegram_notifier import TelegramNotifierError, build_telegram_notifier
from app.sources.base import SourceImage
from app.sources.folder_source import FolderImageSource, folder_image_source
from app.storage.database import init_db
from app.storage.file_store import FileStore, file_store
from config.settings import Settings, get_settings


@dataclass
class FolderWatcherResult:
    """
    单次处理结果。
    """

    source_image: SourceImage
    order: Order | None = None
    success: bool = False
    error: str | None = None


class FolderWatcher:
    """
    本地 incoming 文件夹监听 worker。

    当前版本工作流：

    1. 你把买家图片放进 data/incoming/
    2. watcher 发现图片
    3. 自动创建订单
    4. 把原图复制到订单 original 目录
    5. 根据 IMAGE_PROCESSOR_MODE 决定下一步：

       - local:
         不自动生成 edited
         只通知 Telegram：有新订单待处理，请把修好的图放进 edited/

       - with_api:
         自动调用 order_service.process_order()
         → 生成 edited
         → 再生成 preview
         → Telegram 发预览待审核通知
    """

    def __init__(
        self,
        source: FolderImageSource | None = None,
        service: OrderService | None = None,
        store: FileStore | None = None,
        settings: Settings | None = None,
        auto_process_without_ai: bool = True,
        notify_telegram: bool = True,
    ) -> None:
        self.source = source or folder_image_source
        self.service = service or order_service
        self.store = store or file_store
        self.settings = settings or get_settings()
        self.auto_process_without_ai = auto_process_without_ai
        self.notify_telegram = notify_telegram
        self._running = False

    def run_once(self) -> list[FolderWatcherResult]:
        init_db()
        images = self.source.discover_images()

        if not images:
            logger.debug("No incoming images found")
            return []

        logger.info(f"Discovered {len(images)} incoming image(s)")

        results: list[FolderWatcherResult] = []
        for image in images:
            result = self._handle_source_image(image)
            results.append(result)

        return results

    def run_forever(self) -> None:
        init_db()
        self._running = True

        logger.info("Folder watcher started")
        logger.info(f"Incoming directory: {self.source.incoming_dir}")
        logger.info(f"Watch interval: {self.settings.watch_interval_seconds}s")
        logger.info(f"Telegram notification: {self.notify_telegram}")
        logger.info(f"IMAGE_PROCESSOR_MODE: {getattr(self.settings, 'image_processor_mode', 'local')}")

        try:
            while self._running:
                self.run_once()
                time.sleep(self.settings.watch_interval_seconds)
        except KeyboardInterrupt:
            logger.info("Folder watcher stopped by keyboard interrupt")
        finally:
            self._running = False
            logger.info("Folder watcher stopped")

    def stop(self) -> None:
        self._running = False

    def _handle_source_image(self, source_image: SourceImage) -> FolderWatcherResult:
        result = FolderWatcherResult(source_image=source_image)

        try:
            logger.info(f"Handling image: {source_image.source_path}")

            if not self.store.wait_until_file_stable(source_image.source_path):
                raise RuntimeError(f"File is not stable or timed out: {source_image.source_path}")

            order = self.service.create_order_with_image(
                source_path=source_image.source_path,
                source_type=source_image.source_type,
                buyer_name=source_image.buyer_name,
                buyer_contact=source_image.buyer_contact,
                xianyu_order_id=source_image.xianyu_order_id,
                note=source_image.note,
                extra=source_image.extra or {},
            )
            logger.info(f"Created order: {order.order_id}")

            self.source.mark_consumed(source_image)
            logger.info(f"Moved incoming file to consumed: {source_image.filename}")

            processor_mode = getattr(self.settings, "image_processor_mode", "local")

            if processor_mode == "with_api":
                if self.auto_process_without_ai:
                    logger.info(f"with_api mode detected, processing order: {order.order_id}")
                    try:
                        order = self.service.process_order(order.order_id, processor_mode="with_api")
                    except NotImplementedError as exc:
                        logger.warning(str(exc))
                        order = self.service.mark_failed(order.order_id, str(exc))
                else:
                    logger.info(
                        "with_api mode is enabled, but auto processing is disabled by CLI option. "
                        "Order will remain waiting for external handling."
                    )

                if self.notify_telegram:
                    if order.status == OrderStatus.WAITING_FOR_REVIEW:
                        self._notify_review_if_possible(order)
                    else:
                        self._notify_status_if_possible(order)

            else:
                logger.info(
                    f"local mode detected. Order {order.order_id} will wait for manual edited images."
                )
                if self.notify_telegram:
                    self._notify_pending_processing_if_possible(order, processor_mode="local")

            result.order = order
            result.success = True
            return result

        except Exception as exc:
            logger.exception(f"Failed to handle source image: {source_image.source_path}")
            result.success = False
            result.error = str(exc)

            try:
                self.source.mark_failed(source_image, exc)
            except Exception:
                logger.exception("Failed to mark source image as failed")

            return result

    def _notify_pending_processing_if_possible(self, order: Order, processor_mode: str) -> None:
        """
        local 模式下：
        新订单创建完成后，通知你去手动处理，并把成图放进 edited/。
        """
        if not self.settings.telegram_bot_token or self.settings.telegram_admin_user_id is None:
            logger.warning(
                "Telegram is not configured. Skipped pending-processing notification. "
                "Set TELEGRAM_BOT_TOKEN and TELEGRAM_ADMIN_USER_ID in .env to enable it."
            )
            return

        try:
            notifier = build_telegram_notifier()
            notifier.notify_order_pending_processing(order, processor_mode=processor_mode)
            logger.info(f"Sent pending-processing Telegram notification: {order.order_id}")
        except TelegramNotifierError:
            logger.exception("Failed to send pending-processing Telegram notification")
        except Exception:
            logger.exception("Unexpected error while sending pending-processing notification")

    def _notify_review_if_possible(self, order: Order) -> None:
        """
        preview 已生成，通知进入审核阶段。
        """
        if not self.settings.telegram_bot_token or self.settings.telegram_admin_user_id is None:
            logger.warning(
                "Telegram is not configured. Skipped review notification. "
                "Set TELEGRAM_BOT_TOKEN and TELEGRAM_ADMIN_USER_ID in .env to enable it."
            )
            return

        try:
            notifier = build_telegram_notifier()
            notifier.notify_order_ready_for_review(order)
            logger.info(f"Sent Telegram review notification: {order.order_id}")
        except TelegramNotifierError:
            logger.exception("Failed to send Telegram review notification")
        except Exception:
            logger.exception("Unexpected error while sending Telegram review notification")

    def _notify_status_if_possible(self, order: Order) -> None:
        """
        with_api 模式处理失败时，发一条订单状态通知。
        """
        if not self.settings.telegram_bot_token or self.settings.telegram_admin_user_id is None:
            logger.warning("Telegram is not configured. Skipped order-status notification.")
            return

        try:
            notifier = build_telegram_notifier()
            notifier.notify_order_status(order)
            logger.info(f"Sent Telegram order-status notification: {order.order_id}")
        except TelegramNotifierError:
            logger.exception("Failed to send Telegram order-status notification")
        except Exception:
            logger.exception("Unexpected error while sending Telegram order-status notification")


def build_folder_watcher(
    auto_process_without_ai: bool = True,
    notify_telegram: bool = True,
) -> FolderWatcher:
    return FolderWatcher(
        auto_process_without_ai=auto_process_without_ai,
        notify_telegram=notify_telegram,
    )


def run_folder_watcher(
    once: bool = False,
    auto_process_without_ai: bool = True,
    notify_telegram: bool = True,
) -> list[FolderWatcherResult] | None:
    watcher = build_folder_watcher(
        auto_process_without_ai=auto_process_without_ai,
        notify_telegram=notify_telegram,
    )

    if once:
        return watcher.run_once()

    watcher.run_forever()
    return None