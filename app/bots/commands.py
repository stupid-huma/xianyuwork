from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class BotCommandName(StrEnum):
    """
    Telegram Bot 支持的命令名称。
    """

    START = "start"
    HELP = "help"
    LIST = "list"
    STATUS = "status"
    APPROVE = "approve"
    REJECT = "reject"
    PREVIEW_SENT = "preview_sent"
    BUYER_CONFIRMED = "buyer_confirmed"
    FINAL_SENT = "final_sent"
    COMPLETE = "complete"
    CANCEL = "cancel"
    PROCESS = "process"
    PREVIEWS = "previews"


class CallbackAction(StrEnum):
    """
    Inline button callback 动作。
    """

    APPROVE = "approve"
    REJECT = "reject"
    PREVIEW_SENT = "preview_sent"
    BUYER_CONFIRMED = "buyer_confirmed"
    FINAL_SENT = "final_sent"
    COMPLETE = "complete"
    STATUS = "status"


@dataclass(frozen=True)
class ParsedCommand:
    """
    解析后的命令。

    raw_text: 原始文本
    name: 命令名，不带 /
    args: 参数列表
    """

    raw_text: str
    name: str
    args: list[str]

    @property
    def order_id(self) -> str | None:
        return self.args[0] if self.args else None

    @property
    def message(self) -> str | None:
        if len(self.args) <= 1:
            return None
        return " ".join(self.args[1:]).strip() or None


@dataclass(frozen=True)
class ParsedCallback:
    """
    解析后的按钮回调。

    callback_data 格式：
        action:order_id
    """

    action: CallbackAction
    order_id: str


def parse_command_text(text: str) -> ParsedCommand:
    """
    解析 Telegram 命令文本。

    支持：
        /status ORD_xxx
        /reject ORD_xxx 需要重新处理皮肤细节

    也兼容 bot username：
        /status@YourBot ORD_xxx
    """
    raw_text = text.strip()
    if not raw_text:
        return ParsedCommand(raw_text=text, name="", args=[])

    parts = raw_text.split()
    command = parts[0]

    if command.startswith("/"):
        command = command[1:]

    if "@" in command:
        command = command.split("@", maxsplit=1)[0]

    return ParsedCommand(
        raw_text=text,
        name=command.lower(),
        args=parts[1:],
    )


def parse_callback_data(callback_data: str) -> ParsedCallback:
    """
    解析 InlineKeyboardButton 的 callback_data。
    """
    if ":" not in callback_data:
        raise ValueError(f"Invalid callback_data: {callback_data}")

    action_raw, order_id = callback_data.split(":", maxsplit=1)
    action = CallbackAction(action_raw)

    if not order_id.strip():
        raise ValueError("Callback data missing order_id")

    return ParsedCallback(action=action, order_id=order_id.strip())


def require_order_id(command: ParsedCommand) -> str:
    """
    从命令中提取订单 ID；如果没有则抛出更友好的错误。
    """
    if not command.order_id:
        raise ValueError(
            f"命令 /{command.name} 需要订单 ID，例如：/{command.name} ORD_xxx"
        )

    return command.order_id


def build_help_text() -> str:
    """
    Telegram /help 文本。
    """
    return "\n".join(
        [
            "🤖 <b>闲鱼修图工作流 Bot</b>",
            "",
            "常用命令：",
            "<code>/list</code> - 查看最近订单",
            "<code>/status ORD_xxx</code> - 查看订单状态与建议操作",
            "<code>/process ORD_xxx</code> - 按 settings.py 里的 image_processor_mode 处理。local 模式只提示 edited 目录，api 模式自动处理",
            "<code>/previews ORD_xxx</code> - 重新发送水印预览图给你审核",
            "",
            "审核命令：",
            "<code>/approve ORD_xxx</code> - 内部审核通过，状态进入 review_approved",
            "<code>/reject ORD_xxx 原因</code> - 打回重做，状态进入 rework_required",
            "",
            "交付状态：",
            "<code>/preview_sent ORD_xxx</code> - 标记已把水印预览发给买家",
            "<code>/buyer_confirmed ORD_xxx</code> - 标记买家满意 / 已确认收货",
            "<code>/final_sent ORD_xxx</code> - 准备并标记已发送高清无水印图",
            "<code>/complete ORD_xxx</code> - 完成订单",
            "<code>/cancel ORD_xxx 原因</code> - 取消订单",
            "",
            "推荐流程：",
            "1. 把买家原图放入 <code>data/incoming/</code>",
            "2. worker 自动建单并保存 original，local 模式进入 waiting_for_edited",
            "3. 你手动或用外部工具处理图片，把成图放入订单 edited 目录",
            "4. edited_watcher 自动生成水印 preview，并通知你审核",
            "5. 审核通过后，订单进入 review_approved，但还没有发给买家",
            "6. 你手动发水印预览给买家，再执行 preview_sent",
            "7. 买家确认后，再执行 buyer_confirmed / final_sent / complete",
        ]
    )


def build_start_text() -> str:
    """
    Telegram /start 文本。
    """
    return "\n".join(
        [
            "✅ <b>Bot 已启动</b>",
            "",
            "这是你的闲鱼修图半自动审核助手。",
            "发送 <code>/help</code> 查看可用命令。",
        ]
    )


def build_order_not_found_text(order_id: str) -> str:
    return f"❌ 找不到订单：<code>{escape_html(order_id)}</code>"


def build_error_text(error: Exception) -> str:
    return f"⚠️ 操作失败：<code>{escape_html(str(error))}</code>"


def escape_html(value: object) -> str:
    """
    Telegram HTML parse_mode 下的最小转义。
    """
    text = str(value)
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def shorten_order_id(order_id: str, keep: int = 12) -> str:
    """
    缩短订单 ID，仅用于列表展示。
    """
    if len(order_id) <= keep * 2 + 3:
        return order_id
    return f"{order_id[:keep]}...{order_id[-keep:]}"
