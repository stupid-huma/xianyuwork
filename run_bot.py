from __future__ import annotations

import sys

from loguru import logger

from app.bots.telegram_bot import run_telegram_bot
from app.storage.database import init_db
from config.settings import get_settings


def setup_logging(level: str) -> None:
    logger.remove()
    logger.add(
        sys.stderr,
        level=level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        ),
    )


def main() -> None:
    """
    Telegram Bot 启动入口。

    启动前需要在 .env 中配置：
        TELEGRAM_BOT_TOKEN=你的 Bot Token
        TELEGRAM_ADMIN_USER_ID=你的 Telegram 数字 ID

    启动命令：
        python run_bot.py
    """
    settings = get_settings()
    setup_logging(settings.log_level)

    try:
        settings.validate_telegram_config()
        init_db()

        logger.info("Starting Xianyu photo workflow Telegram bot")
        logger.info(f"App env: {settings.app_env}")
        logger.info(f"Database path: {settings.database_path}")
        logger.info(f"Admin user id: {settings.telegram_admin_user_id}")

        run_telegram_bot()

    except ValueError as exc:
        logger.error(str(exc))
        logger.error(
            "Please check your .env file. Required fields: "
            "TELEGRAM_BOT_TOKEN and TELEGRAM_ADMIN_USER_ID"
        )
        raise SystemExit(1) from exc
    except KeyboardInterrupt:
        logger.info("Telegram bot stopped by keyboard interrupt")
    except Exception as exc:
        logger.exception(f"Telegram bot crashed: {exc}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
