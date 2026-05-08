from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# 把这里换成 BotFather 给你的 Token
BOT_TOKEN = "8630289562:AAHm7Q3G_v8IY_fPyg9XurhoqrWO9Sc1SvE"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "你好，我是你的 TG 机器人。\n\n"
        "你可以给我发文字、图片，或者发送 /help 查看功能。"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "目前支持：\n"
        "/start - 启动机器人\n"
        "/help - 查看帮助\n"
        "发送文字 - 我会回复你\n"
        "发送图片 - 我会告诉你已收到图片"
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text

    if "你好" in user_text:
        reply = "你好！很高兴见到你。"
    elif "图片" in user_text:
        reply = "你可以直接把图片发给我。"
    elif "订单" in user_text:
        reply = "我可以帮你记录订单，不过现在只是测试版。"
    else:
        reply = f"你刚才说的是：{user_text}"

    await update.message.reply_text(reply)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo = update.message.photo[-1]

    file = await photo.get_file()
    await file.download_to_drive("received_photo.jpg")

    await update.message.reply_text(
        "图片已收到，并保存为 received_photo.jpg"
    )


async def handle_unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("这个内容我暂时还不会处理。")


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    app.add_handler(MessageHandler(filters.ALL, handle_unknown))

    print("机器人已启动，正在监听消息...")
    app.run_polling()


if __name__ == "__main__":
    main()