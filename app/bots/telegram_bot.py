from __future__ import annotations

from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from app.bots.commands import (
    BotCommandName,
    CallbackAction,
    build_error_text,
    build_help_text,
    build_order_not_found_text,
    build_start_text,
    escape_html,
    parse_callback_data,
    parse_command_text,
    require_order_id,
    shorten_order_id,
)
from app.core.enums import OrderStatus, ReviewDecision
from app.core.order_service import OrderNotFoundError, OrderService, order_service
from app.storage.database import init_db
from config.paths import get_project_paths
from config.settings import Settings, get_settings


class TelegramWorkflowBot:
    """
    闲鱼修图工作流 Telegram Bot。

    职责：
    - 接收你的 Telegram 命令
    - 接收 inline button 回调
    - 调用 OrderService 推进状态机
    - 把订单状态、预览图、最终图发回给你

    注意：
    - 只允许 TELEGRAM_ADMIN_USER_ID 对应的用户操作
    - 不直接处理闲鱼消息
    - 不直接调用 OpenAI API
    """

    def __init__(
        self,
        settings: Settings | None = None,
        service: OrderService | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.settings.validate_telegram_config()

        self.service = service or order_service
        self.admin_user_id = self.settings.telegram_admin_user_id

    def build_application(self) -> Application:
        """
        创建 python-telegram-bot Application。
        """
        application = ApplicationBuilder().token(self.settings.telegram_bot_token).build()

        application.add_handler(CommandHandler(BotCommandName.START.value, self.handle_start))
        application.add_handler(CommandHandler(BotCommandName.HELP.value, self.handle_help))
        application.add_handler(CommandHandler(BotCommandName.LIST.value, self.handle_list))
        application.add_handler(CommandHandler(BotCommandName.STATUS.value, self.handle_status))
        application.add_handler(CommandHandler(BotCommandName.PROCESS.value, self.handle_process))
        application.add_handler(CommandHandler(BotCommandName.PREVIEWS.value, self.handle_previews))

        application.add_handler(CommandHandler(BotCommandName.APPROVE.value, self.handle_approve))
        application.add_handler(CommandHandler(BotCommandName.REJECT.value, self.handle_reject))

        application.add_handler(
            CommandHandler(BotCommandName.PREVIEW_SENT.value, self.handle_preview_sent)
        )
        application.add_handler(
            CommandHandler(BotCommandName.BUYER_CONFIRMED.value, self.handle_buyer_confirmed)
        )
        application.add_handler(
            CommandHandler(BotCommandName.FINAL_SENT.value, self.handle_final_sent)
        )
        application.add_handler(CommandHandler(BotCommandName.COMPLETE.value, self.handle_complete))
        application.add_handler(CommandHandler(BotCommandName.CANCEL.value, self.handle_cancel))

        application.add_handler(CallbackQueryHandler(self.handle_callback))

        return application

    # ------------------------------------------------------------------
    # Basic commands
    # ------------------------------------------------------------------

    async def handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._ensure_admin(update):
            return
        await self._reply_text(update, build_start_text())

    async def handle_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._ensure_admin(update):
            return
        await self._reply_text(update, build_help_text())

    async def handle_list(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._ensure_admin(update):
            return

        try:
            status = self._parse_optional_status(context.args)
            orders = self.service.list_orders(status=status, limit=20)

            if not orders:
                if status:
                    await self._reply_text(update, f"暂无 <code>{status.value}</code> 状态的订单。")
                else:
                    await self._reply_text(update, "暂无订单。")
                return

            lines = ["📋 <b>最近订单</b>", ""]
            for order in orders:
                lines.append(
                    f"- <code>{escape_html(shorten_order_id(order.order_id))}</code> | "
                    f"<code>{order.status.value}</code> | "
                    f"图片 {order.image_count} 张 | "
                    f"<code>{order.created_at.strftime('%m-%d %H:%M')}</code>"
                )
                lines.append(f"  <code>/status {escape_html(order.order_id)}</code>")

            await self._reply_text(update, "\n".join(lines))
        except Exception as exc:
            await self._reply_text(update, build_error_text(exc))

    async def handle_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._ensure_admin(update):
            return

        try:
            command = self._parse_update_command(update)
            order_id = require_order_id(command)
            order = self.service.get_order(order_id)

            await self._reply_text(update, self._format_order_status(order_id=order.order_id))
            await self._reply_text(update, self._format_order_detail(order.order_id))
        except OrderNotFoundError:
            order_id = self._first_arg(context.args) or ""
            await self._reply_text(update, build_order_not_found_text(order_id))
        except Exception as exc:
            await self._reply_text(update, build_error_text(exc))

    # ------------------------------------------------------------------
    # Processing commands
    # ------------------------------------------------------------------

    async def handle_process(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        按 IMAGE_PROCESSOR_MODE 处理订单。

        - local：不自动处理，只提示把成图放入 edited/
        - with_api：后续接 API 后通过 OrderService.process_order() 处理
        """
        if not await self._ensure_admin(update):
            return

        try:
            command = self._parse_update_command(update)
            order_id = require_order_id(command)

            if self.settings.image_processor_mode == "local":
                edited_dir = get_project_paths().edited_dir(order_id)
                await self._reply_text(
                    update,
                    "ℹ️ 当前是 <code>local</code> 模式，不会自动生成 edited 图。\n\n"
                    "请手动或用外部工具处理图片，然后把成图放入：\n"
                    f"<code>{escape_html(edited_dir.as_posix())}</code>\n\n"
                    "之后 edited_watcher 会自动生成水印预览图并通知你审核。",
                )
                return

            order = self.service.process_order(order_id)
            await self._reply_text(
                update,
                f"✅ 已处理并生成水印预览图，订单进入：<code>{order.status.value}</code>",
                reply_markup=self._build_review_keyboard(order.order_id),
            )
            await self._send_preview_images(update, order.order_id)
        except Exception as exc:
            await self._reply_text(update, build_error_text(exc))

    async def handle_previews(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._ensure_admin(update):
            return

        try:
            command = self._parse_update_command(update)
            order_id = require_order_id(command)
            await self._send_preview_images(update, order_id)
        except Exception as exc:
            await self._reply_text(update, build_error_text(exc))

    # ------------------------------------------------------------------
    # Review commands
    # ------------------------------------------------------------------

    async def handle_approve(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._ensure_admin(update):
            return

        try:
            command = self._parse_update_command(update)
            order_id = require_order_id(command)
            order = self.service.review_order(
                order_id=order_id,
                decision=ReviewDecision.APPROVE,
                message=command.message,
            )
            await self._reply_text(
                update,
                f"✅ 审核通过。订单状态：<code>{order.status.value}</code>\n\n"
                "注意：这只代表你内部审核通过，还没有发给买家。\n"
                "下一步：把水印预览图发给买家，然后执行：\n"
                f"<code>/preview_sent {order.order_id}</code>",
                reply_markup=self._build_after_approve_keyboard(order.order_id),
            )
        except Exception as exc:
            await self._reply_text(update, build_error_text(exc))

    async def handle_reject(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._ensure_admin(update):
            return

        try:
            command = self._parse_update_command(update)
            order_id = require_order_id(command)
            order = self.service.review_order(
                order_id=order_id,
                decision=ReviewDecision.REJECT,
                message=command.message or "Telegram command rejected",
            )
            edited_dir = get_project_paths().edited_dir(order.order_id)
            await self._reply_text(
                update,
                f"❌ 已打回重做。订单状态：<code>{order.status.value}</code>\n"
                f"原因：<code>{escape_html(command.message or '未填写')}</code>\n\n"
                "请重新处理图片，并把新成图放入：\n"
                f"<code>{escape_html(edited_dir.as_posix())}</code>",
            )
        except Exception as exc:
            await self._reply_text(update, build_error_text(exc))

    # ------------------------------------------------------------------
    # Delivery state commands
    # ------------------------------------------------------------------

    async def handle_preview_sent(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._ensure_admin(update):
            return

        try:
            command = self._parse_update_command(update)
            order_id = require_order_id(command)
            order = self.service.mark_preview_sent(order_id)
            await self._reply_text(
                update,
                f"📤 已标记水印预览图发给买家。订单状态：<code>{order.status.value}</code>\n\n"
                "买家满意 / 确认收货后执行：\n"
                f"<code>/buyer_confirmed {order.order_id}</code>",
                reply_markup=self._build_after_preview_sent_keyboard(order.order_id),
            )
        except Exception as exc:
            await self._reply_text(update, build_error_text(exc))

    async def handle_buyer_confirmed(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._ensure_admin(update):
            return

        try:
            command = self._parse_update_command(update)
            order_id = require_order_id(command)
            order = self.service.mark_buyer_confirmed(order_id)
            await self._reply_text(
                update,
                f"✅ 已标记买家确认。订单状态：<code>{order.status.value}</code>\n\n"
                "现在可以准备发送高清无水印图：\n"
                f"<code>/final_sent {order.order_id}</code>",
                reply_markup=self._build_after_buyer_confirmed_keyboard(order.order_id),
            )
        except Exception as exc:
            await self._reply_text(update, build_error_text(exc))

    async def handle_final_sent(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._ensure_admin(update):
            return

        try:
            command = self._parse_update_command(update)
            order_id = require_order_id(command)
            order = self.service.mark_final_sent(order_id)

            await self._reply_text(
                update,
                f"📦 已准备最终高清图，并标记已发送。订单状态：<code>{order.status.value}</code>\n"
                "下面发送 final 目录中的高清文件给你备份。",
                reply_markup=self._build_after_final_sent_keyboard(order.order_id),
            )
            await self._send_final_images(update, order.order_id)
            await self._reply_text(
                update,
                f"确认订单结束后执行：\n<code>/complete {order.order_id}</code>",
            )
        except Exception as exc:
            await self._reply_text(update, build_error_text(exc))

    async def handle_complete(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._ensure_admin(update):
            return

        try:
            command = self._parse_update_command(update)
            order_id = require_order_id(command)
            order = self.service.complete_order(order_id)
            await self._reply_text(
                update,
                f"🎉 订单已完成：<code>{order.order_id}</code>",
            )
        except Exception as exc:
            await self._reply_text(update, build_error_text(exc))

    async def handle_cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._ensure_admin(update):
            return

        try:
            command = self._parse_update_command(update)
            order_id = require_order_id(command)
            order = self.service.cancel_order(order_id, message=command.message)
            await self._reply_text(
                update,
                f"🚫 订单已取消：<code>{order.order_id}</code>\n"
                f"状态：<code>{order.status.value}</code>",
            )
        except Exception as exc:
            await self._reply_text(update, build_error_text(exc))

    # ------------------------------------------------------------------
    # Button callback
    # ------------------------------------------------------------------

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._ensure_admin(update):
            return

        query = update.callback_query
        if query is None or query.data is None:
            return

        try:
            parsed = parse_callback_data(query.data)
            await query.answer()

            if parsed.action == CallbackAction.APPROVE:
                order = self.service.approve_review(parsed.order_id, message="Approved by button")
                await query.edit_message_text(
                    text=(
                        "✅ 审核通过。\n"
                        f"订单：<code>{order.order_id}</code>\n"
                        f"状态：<code>{order.status.value}</code>\n\n"
                        "下一步：把水印预览图发给买家后，点击下方按钮。"
                    ),
                    parse_mode=ParseMode.HTML,
                    reply_markup=self._build_after_approve_keyboard(order.order_id),
                )
                return

            if parsed.action == CallbackAction.REJECT:
                order = self.service.reject_review(parsed.order_id, message="Rejected by button")
                edited_dir = get_project_paths().edited_dir(order.order_id)
                await query.edit_message_text(
                    text=(
                        "❌ 已打回重做。\n"
                        f"订单：<code>{order.order_id}</code>\n"
                        f"状态：<code>{order.status.value}</code>\n\n"
                        "请把重修后的成图放入：\n"
                        f"<code>{escape_html(edited_dir.as_posix())}</code>"
                    ),
                    parse_mode=ParseMode.HTML,
                )
                return

            if parsed.action == CallbackAction.PREVIEW_SENT:
                order = self.service.mark_preview_sent(parsed.order_id)
                await query.edit_message_text(
                    text=(
                        "📤 已标记预览图发给买家。\n"
                        f"订单：<code>{order.order_id}</code>\n"
                        f"状态：<code>{order.status.value}</code>"
                    ),
                    parse_mode=ParseMode.HTML,
                    reply_markup=self._build_after_preview_sent_keyboard(order.order_id),
                )
                return

            if parsed.action == CallbackAction.BUYER_CONFIRMED:
                order = self.service.mark_buyer_confirmed(parsed.order_id)
                await query.edit_message_text(
                    text=(
                        "✅ 已标记买家确认。\n"
                        f"订单：<code>{order.order_id}</code>\n"
                        f"状态：<code>{order.status.value}</code>"
                    ),
                    parse_mode=ParseMode.HTML,
                    reply_markup=self._build_after_buyer_confirmed_keyboard(order.order_id),
                )
                return

            if parsed.action == CallbackAction.FINAL_SENT:
                order = self.service.mark_final_sent(parsed.order_id)
                await query.edit_message_text(
                    text=(
                        "📦 已准备最终高清图，并标记已发送。\n"
                        f"订单：<code>{order.order_id}</code>\n"
                        f"状态：<code>{order.status.value}</code>"
                    ),
                    parse_mode=ParseMode.HTML,
                    reply_markup=self._build_after_final_sent_keyboard(order.order_id),
                )
                await self._send_final_images(update, order.order_id)
                return

            if parsed.action == CallbackAction.COMPLETE:
                order = self.service.complete_order(parsed.order_id)
                await query.edit_message_text(
                    text=f"🎉 订单已完成：<code>{order.order_id}</code>",
                    parse_mode=ParseMode.HTML,
                )
                return

            if parsed.action == CallbackAction.STATUS:
                await query.message.reply_text(
                    self._format_order_detail(parsed.order_id),
                    parse_mode=ParseMode.HTML,
                )
                return

            await query.answer("暂不支持的操作", show_alert=True)
        except Exception as exc:
            if query:
                await query.answer("操作失败", show_alert=True)
                await query.message.reply_text(build_error_text(exc), parse_mode=ParseMode.HTML)

    # ------------------------------------------------------------------
    # Send files
    # ------------------------------------------------------------------

    async def _send_preview_images(self, update: Update, order_id: str) -> None:
        order = self.service.get_order(order_id)
        preview_paths = order.preview_paths

        if not preview_paths:
            await self._reply_text(update, f"⚠️ 订单 <code>{order.order_id}</code> 暂无水印预览图。")
            return

        for index, path in enumerate(preview_paths, start=1):
            await self._send_photo(
                update,
                path,
                caption=(
                    f"🖼️ 水印预览图 {index}/{len(preview_paths)}\n"
                    f"订单：<code>{order.order_id}</code>"
                ),
            )

    async def _send_final_images(self, update: Update, order_id: str) -> None:
        order = self.service.get_order(order_id)
        final_paths = order.final_paths

        if not final_paths:
            await self._reply_text(update, f"⚠️ 订单 <code>{order.order_id}</code> 暂无最终高清图。")
            return

        for index, path in enumerate(final_paths, start=1):
            await self._send_document(
                update,
                path,
                caption=(
                    f"📦 最终高清图 {index}/{len(final_paths)}\n"
                    f"订单：<code>{order.order_id}</code>"
                ),
            )

    # ------------------------------------------------------------------
    # Formatters
    # ------------------------------------------------------------------

    def _format_order_status(self, order_id: str) -> str:
        order = self.service.get_order(order_id)
        return (
            f"📌 <b>订单状态</b>\n\n"
            f"订单 ID：<code>{order.order_id}</code>\n"
            f"状态：<code>{order.status.value}</code>\n"
            f"图片数量：<b>{order.image_count}</b>\n"
            f"创建时间：<code>{order.created_at.strftime('%Y-%m-%d %H:%M:%S')}</code>\n"
            f"更新时间：<code>{order.updated_at.strftime('%Y-%m-%d %H:%M:%S')}</code>"
        )

    def _format_order_detail(self, order_id: str) -> str:
        order = self.service.get_order(order_id)

        lines = [
            "🧾 <b>订单详情</b>",
            "",
            f"订单 ID：<code>{order.order_id}</code>",
            f"状态：<code>{order.status.value}</code>",
            f"来源：<code>{order.source_type.value}</code>",
            f"图片数量：<b>{order.image_count}</b>",
        ]

        if order.buyer_name:
            lines.append(f"买家：{escape_html(order.buyer_name)}")

        if order.xianyu_order_id:
            lines.append(f"闲鱼订单号：<code>{escape_html(order.xianyu_order_id)}</code>")

        if order.note:
            lines.append(f"备注：{escape_html(order.note)}")

        if order.error_message:
            lines.append(f"错误：<code>{escape_html(order.error_message)}</code>")

        if order.images:
            lines.extend(["", "图片列表："])
            for image in order.images:
                lines.append(
                    f"- <code>{image.image_id}</code> | "
                    f"<code>{image.status.value}</code> | "
                    f"{escape_html(image.filename)}"
                )

        actions = self._available_actions(order)
        if actions:
            lines.extend(["", "当前建议操作："])
            lines.extend(actions)

        return "\n".join(lines)

    def _available_actions(self, order) -> list[str]:
        if order.status in {OrderStatus.WAITING_FOR_EDITED, OrderStatus.REWORK_REQUIRED}:
            edited_dir = get_project_paths().edited_dir(order.order_id)
            return [
                "把处理完成的图片放入：",
                f"<code>{escape_html(edited_dir.as_posix())}</code>",
                f"<code>/status {order.order_id}</code>",
            ]

        if order.status == OrderStatus.WAITING_FOR_REVIEW:
            return [
                f"<code>/previews {order.order_id}</code>",
                f"<code>/approve {order.order_id}</code>",
                f"<code>/reject {order.order_id} 原因</code>",
            ]

        if order.status == OrderStatus.REVIEW_APPROVED:
            return [f"<code>/preview_sent {order.order_id}</code>"]

        if order.status == OrderStatus.PREVIEW_SENT:
            return [f"<code>/buyer_confirmed {order.order_id}</code>"]

        if order.status == OrderStatus.BUYER_CONFIRMED:
            return [f"<code>/final_sent {order.order_id}</code>"]

        if order.status == OrderStatus.FINAL_SENT:
            return [f"<code>/complete {order.order_id}</code>"]

        if order.status in {OrderStatus.IMAGES_RECEIVED, OrderStatus.PROCESSING, OrderStatus.FAILED}:
            return [f"<code>/process {order.order_id}</code>"]

        return []

    # ------------------------------------------------------------------
    # Keyboards
    # ------------------------------------------------------------------

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

    def _build_after_approve_keyboard(self, order_id: str) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("📤 已发预览", callback_data=f"preview_sent:{order_id}"),
                ],
                [
                    InlineKeyboardButton("📌 查看状态", callback_data=f"status:{order_id}"),
                ],
            ]
        )

    def _build_after_preview_sent_keyboard(self, order_id: str) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("✅ 买家已确认", callback_data=f"buyer_confirmed:{order_id}"),
                ],
                [
                    InlineKeyboardButton("📌 查看状态", callback_data=f"status:{order_id}"),
                ],
            ]
        )

    def _build_after_buyer_confirmed_keyboard(self, order_id: str) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("📦 已发高清", callback_data=f"final_sent:{order_id}"),
                ],
                [
                    InlineKeyboardButton("📌 查看状态", callback_data=f"status:{order_id}"),
                ],
            ]
        )

    def _build_after_final_sent_keyboard(self, order_id: str) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("🎉 完成订单", callback_data=f"complete:{order_id}"),
                ],
                [
                    InlineKeyboardButton("📌 查看状态", callback_data=f"status:{order_id}"),
                ],
            ]
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _ensure_admin(self, update: Update) -> bool:
        user = update.effective_user
        allowed = user is not None and user.id == self.admin_user_id

        if allowed:
            return True

        if update.callback_query is not None:
            await update.callback_query.answer("无权限", show_alert=True)
            return False

        if update.effective_message is not None:
            await update.effective_message.reply_text("⛔ 你没有权限操作这个 Bot。")

        return False

    async def _reply_text(
        self,
        update: Update,
        text: str,
        reply_markup: InlineKeyboardMarkup | None = None,
    ) -> None:
        if update.effective_message is not None:
            await update.effective_message.reply_text(
                text=text,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
                reply_markup=reply_markup,
            )

    async def _send_photo(self, update: Update, path: Path, caption: str | None = None) -> None:
        if update.effective_chat is None:
            return

        with path.open("rb") as file:
            await update.effective_chat.send_photo(
                photo=file,
                caption=caption,
                parse_mode=ParseMode.HTML,
            )

    async def _send_document(self, update: Update, path: Path, caption: str | None = None) -> None:
        if update.effective_chat is None:
            return

        with path.open("rb") as file:
            await update.effective_chat.send_document(
                document=file,
                caption=caption,
                parse_mode=ParseMode.HTML,
            )

    def _parse_update_command(self, update: Update):
        text = ""
        if update.effective_message and update.effective_message.text:
            text = update.effective_message.text
        return parse_command_text(text)

    def _first_arg(self, args: list[str] | tuple[str, ...] | None) -> str | None:
        return args[0] if args else None

    def _parse_optional_status(self, args: list[str] | tuple[str, ...] | None) -> OrderStatus | None:
        if not args:
            return None
        return OrderStatus(args[0].strip().lower())


def build_telegram_application() -> Application:
    """
    构建 Telegram Application。
    run_bot.py 会调用它。
    """
    init_db()
    bot = TelegramWorkflowBot()
    return bot.build_application()


def run_telegram_bot() -> None:
    """
    启动 Telegram Bot 长轮询。
    """
    application = build_telegram_application()
    application.run_polling(allowed_updates=Update.ALL_TYPES)
