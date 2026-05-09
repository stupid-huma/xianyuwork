from __future__ import annotations

import asyncio
from pathlib import Path

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError

from app.core.models import Order
from config.paths import get_project_paths
from config.settings import Settings, get_settings


class TelegramNotifierError(RuntimeError):
    """
    Telegram 通知发送失败。
    """


class TelegramNotifier:
    """
    Telegram 通知器。

    当前版本支持两类通知：
    1. 新订单待处理（还没有 preview，只提醒你去处理并把成图放进 edited/）
    2. preview 已生成，进入审核阶段
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.settings.validate_telegram_config()

        self.bot = Bot(token=self.settings.telegram_bot_token)
        self.admin_user_id = self.settings.telegram_admin_user_id

        if self.admin_user_id is None:
            raise TelegramNotifierError("TELEGRAM_ADMIN_USER_ID is required")

    # ------------------------------------------------------------------
    # Sync wrappers
    # ------------------------------------------------------------------

    def send_text(self, text: str) -> None:
        self._run_sync(self.async_send_text(text))

    def send_photo(self, photo_path: Path, caption: str | None = None) -> None:
        self._run_sync(self.async_send_photo(photo_path, caption=caption))

    def send_document(self, document_path: Path, caption: str | None = None) -> None:
        self._run_sync(self.async_send_document(document_path, caption=caption))

    def notify_order_pending_processing(self, order: Order, processor_mode: str = "local") -> None:
        self._run_sync(self.async_notify_order_pending_processing(order, processor_mode=processor_mode))

    def notify_order_ready_for_review(self, order: Order) -> None:
        self._run_sync(self.async_notify_order_ready_for_review(order))

    def notify_order_status(self, order: Order) -> None:
        self._run_sync(self.async_notify_order_status(order))

    def send_preview_images(self, order: Order) -> None:
        self._run_sync(self.async_send_preview_images(order))

    def send_final_images(self, order: Order) -> None:
        self._run_sync(self.async_send_final_images(order))

    # ------------------------------------------------------------------
    # Async methods
    # ------------------------------------------------------------------

    async def async_send_text(self, text: str) -> None:
        try:
            await self.bot.send_message(
                chat_id=self.admin_user_id,
                text=text,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
        except TelegramError as exc:
            raise TelegramNotifierError(f"Failed to send Telegram message: {exc}") from exc

    async def async_send_photo(self, photo_path: Path, caption: str | None = None) -> None:
        self._validate_file(photo_path)

        try:
            with photo_path.open("rb") as file:
                await self.bot.send_photo(
                    chat_id=self.admin_user_id,
                    photo=file,
                    caption=caption,
                    parse_mode="HTML",
                )
        except TelegramError as exc:
            raise TelegramNotifierError(f"Failed to send Telegram photo: {exc}") from exc

    async def async_send_document(
        self,
        document_path: Path,
        caption: str | None = None,
    ) -> None:
        self._validate_file(document_path)

        try:
            with document_path.open("rb") as file:
                await self.bot.send_document(
                    chat_id=self.admin_user_id,
                    document=file,
                    caption=caption,
                    parse_mode="HTML",
                )
        except TelegramError as exc:
            raise TelegramNotifierError(f"Failed to send Telegram document: {exc}") from exc

    async def async_notify_order_pending_processing(
        self,
        order: Order,
        processor_mode: str = "local",
    ) -> None:
        """
        新订单已进入系统，但还没有 preview。
        这时只提醒你去处理，并把成品放到 edited/。
        """
        text = self._format_order_pending_processing_text(order, processor_mode=processor_mode)

        try:
            await self.bot.send_message(
                chat_id=self.admin_user_id,
                text=text,
                parse_mode="HTML",
                disable_web_page_preview=True,
                reply_markup=self._build_pending_processing_keyboard(order.order_id),
            )
        except TelegramError as exc:
            raise TelegramNotifierError(
                f"Failed to send pending-processing message: {exc}"
            ) from exc

    async def async_notify_order_ready_for_review(self, order: Order) -> None:
        """
        preview 已生成，发送审核通知。
        """
        text = self._format_order_review_text(order)
        keyboard = self._build_review_keyboard(order.order_id)

        try:
            await self.bot.send_message(
                chat_id=self.admin_user_id,
                text=text,
                parse_mode="HTML",
                disable_web_page_preview=True,
                reply_markup=keyboard,
            )
        except TelegramError as exc:
            raise TelegramNotifierError(f"Failed to send review message: {exc}") from exc

        await self.async_send_preview_images(order)

    async def async_notify_order_status(self, order: Order) -> None:
        text = self._format_order_status_text(order)
        await self.async_send_text(text)

    async def async_send_preview_images(self, order: Order) -> None:
        preview_paths = order.preview_paths

        if not preview_paths:
            await self.async_send_text(
                f"⚠️ 订单 <code>{order.order_id}</code> 暂无水印预览图。"
            )
            return

        for index, path in enumerate(preview_paths, start=1):
            caption = (
                f"🖼️ 水印预览图 {index}/{len(preview_paths)}\n"
                f"订单：<code>{order.order_id}</code>"
            )
            await self.async_send_photo(path, caption=caption)

    async def async_send_final_images(self, order: Order) -> None:
        final_paths = order.final_paths

        if not final_paths:
            await self.async_send_text(
                f"⚠️ 订单 <code>{order.order_id}</code> 暂无最终高清图。"
            )
            return

        for index, path in enumerate(final_paths, start=1):
            caption = (
                f"📦 最终高清图 {index}/{len(final_paths)}\n"
                f"订单：<code>{order.order_id}</code>"
            )
            await self.async_send_document(path, caption=caption)

    # ------------------------------------------------------------------
    # Text formatting
    # ------------------------------------------------------------------

    def _format_order_pending_processing_text(
        self,
        order: Order,
        processor_mode: str = "local",
    ) -> str:
        paths = get_project_paths()
        edited_dir = paths.edited_dir(order.order_id)

        mode_text = (
            "手动处理模式（local）"
            if processor_mode == "local"
            else "自动处理模式（with_api）"
        )

        lines = [
            "🆕 <b>新订单已创建，等待处理</b>",
            "",
            f"订单 ID：<code>{order.order_id}</code>",
            f"当前状态：<code>{order.status.value}</code>",
            f"图片数量：<b>{order.image_count}</b>",
            f"处理模式：<code>{self._escape(mode_text)}</code>",
        ]

        if order.buyer_name:
            lines.append(f"买家：{self._escape(order.buyer_name)}")

        if order.xianyu_order_id:
            lines.append(f"闲鱼订单号：<code>{self._escape(order.xianyu_order_id)}</code>")

        lines.extend(
            [
                "",
                "当前还没有 preview 图。",
                "请先完成图片处理，再放入 edited 目录：",
                f"<code>{self._escape(edited_dir.as_posix())}</code>",
            ]
        )

        if processor_mode == "local":
            lines.extend(
                [
                    "",
                    "处理说明：",
                    "1. 你手动修图或用外部工具处理",
                    "2. 把修好的成图放入上面的 edited 目录",
                    "3. edited_watcher 会自动生成 preview 并通知你审核",
                ]
            )
        else:
            lines.extend(
                [
                    "",
                    "处理说明：",
                    "系统将尝试自动处理图片；如果失败，你也可以手动把成图放入 edited 目录。",
                ]
            )

        lines.extend(
            [
                "",
                "常用命令：",
                f"<code>/status {order.order_id}</code>",
                f"<code>/previews {order.order_id}</code>",
            ]
        )

        return "\n".join(lines)

    def _format_order_review_text(self, order: Order) -> str:
        lines = [
            "🧾 <b>订单预览已生成，等待审核</b>",
            "",
            f"订单 ID：<code>{order.order_id}</code>",
            f"当前状态：<code>{order.status.value}</code>",
            f"图片数量：<b>{order.image_count}</b>",
        ]

        if order.buyer_name:
            lines.append(f"买家：{self._escape(order.buyer_name)}")

        if order.xianyu_order_id:
            lines.append(f"闲鱼订单号：<code>{self._escape(order.xianyu_order_id)}</code>")

        if order.note:
            lines.extend(["", f"备注：{self._escape(order.note)}"])

        lines.extend(
            [
                "",
                "此阶段只做内部审核；审核通过不等于已经发给买家。",
                "你可以点击按钮审核，也可以使用命令：",
                f"<code>/approve {order.order_id}</code>",
                f"<code>/reject {order.order_id} 需要重做的原因</code>",
                f"<code>/status {order.order_id}</code>",
            ]
        )

        return "\n".join(lines)

    def _format_order_status_text(self, order: Order) -> str:
        lines = [
            "📌 <b>订单状态</b>",
            "",
            f"订单 ID：<code>{order.order_id}</code>",
            f"状态：<code>{order.status.value}</code>",
            f"图片数量：<b>{order.image_count}</b>",
            f"创建时间：<code>{order.created_at.strftime('%Y-%m-%d %H:%M:%S')}</code>",
            f"更新时间：<code>{order.updated_at.strftime('%Y-%m-%d %H:%M:%S')}</code>",
        ]

        if order.error_message:
            lines.extend(["", f"错误：<code>{self._escape(order.error_message)}</code>"])

        if order.images:
            lines.extend(["", "图片："])
            for image in order.images:
                lines.append(
                    f"- <code>{image.image_id}</code> | "
                    f"<code>{image.status.value}</code> | "
                    f"{self._escape(image.filename)}"
                )

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Keyboards
    # ------------------------------------------------------------------

    def _build_pending_processing_keyboard(self, order_id: str) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("📌 查看状态", callback_data=f"status:{order_id}"),
                ],
            ]
        )

    def _build_review_keyboard(self, order_id: str) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("✅ 审核通过", callback_data=f"approve:{order_id}"),
                    InlineKeyboardButton("❌ 打回重做", callback_data=f"reject:{order_id}"),
                ],
                [
                    InlineKeyboardButton("📌 查看状态", callback_data=f"status:{order_id}"),
                ],
            ]
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _validate_file(self, path: Path) -> None:
        if not path.exists():
            raise FileNotFoundError(f"Telegram file does not exist: {path}")

        if not path.is_file():
            raise ValueError(f"Telegram path is not a file: {path}")

    def _run_sync(self, coroutine) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(coroutine)
            return

        if loop.is_running():
            raise TelegramNotifierError(
                "TelegramNotifier sync method was called inside a running event loop. "
                "Use the async_* method instead."
            )

        loop.run_until_complete(coroutine)

    def _escape(self, value: object) -> str:
        text = str(value)
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )


def build_telegram_notifier() -> TelegramNotifier:
    return TelegramNotifier()
