from __future__ import annotations

import sys

from loguru import logger

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


def print_project_status() -> None:
    """
    打印当前项目状态。

    这个入口不启动 worker，也不启动 Telegram Bot。
    它只用于确认：
    - .env 能否读取
    - 目录能否创建
    - 数据库能否初始化
    - Telegram 配置是否填写
    """
    settings = get_settings()
    setup_logging(settings.log_level)

    logger.info("Initializing Xianyu photo workflow project")
    init_db()

    print()
    print("✅ Xianyu Photo Workflow initialized")
    print()
    print("Project paths:")
    print(f"  DATA_DIR      = {settings.data_dir}")
    print(f"  INCOMING_DIR  = {settings.incoming_dir}")
    print(f"  ORDERS_DIR    = {settings.orders_dir}")
    print(f"  DATABASE_PATH = {settings.database_path}")
    print()
    print("Image settings:")
    print(f"  WATERMARK_TEXT     = {settings.watermark_text}")
    print(f"  WATERMARK_OPACITY  = {settings.watermark_opacity}")
    print(f"  PREVIEW_MAX_SIZE   = {settings.preview_max_size}")
    print(f"  SUPPORTED_FORMATS  = {', '.join(settings.supported_image_extensions)}")
    print()
    print("Telegram:")
    print(f"  TELEGRAM_BOT_TOKEN configured     = {bool(settings.telegram_bot_token)}")
    print(f"  TELEGRAM_ADMIN_USER_ID configured = {settings.telegram_admin_user_id is not None}")
    print()
    print("Next commands:")
    print("  1. Test worker once without Telegram:")
    print("     python run_worker.py --once --no-telegram")
    print()
    print("  2. Run folder watcher continuously:")
    print("     python run_worker.py")
    print()
    print("  3. Run Telegram bot:")
    print("     python run_bot.py")
    print()


def main() -> None:
    try:
        print_project_status()
    except Exception as exc:
        logger.exception(f"Project initialization failed: {exc}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
