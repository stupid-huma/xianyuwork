from __future__ import annotations

import argparse
import sys
import threading
import time
from typing import Literal

from loguru import logger

from app.storage.database import init_db
from app.workers.edited_watcher import build_edited_watcher, run_edited_watcher
from app.workers.folder_watcher import build_folder_watcher, run_folder_watcher
from config.settings import get_settings


WorkerMode = Literal["folder", "edited", "both"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run xianyu photo workflow workers.",
    )

    parser.add_argument(
        "--mode",
        choices=["folder", "edited", "both"],
        default="both",
        help="Worker mode. folder=监听 incoming，edited=监听人工修图回流，both=两个都运行。默认 both。",
    )

    parser.add_argument(
        "--once",
        action="store_true",
        help="只扫描并处理一次，然后退出。适合调试。",
    )

    parser.add_argument(
        "--no-auto-process",
        action="store_true",
        help=(
            "关闭 with_api 自动处理。local 模式本来不会自动生成 edited/preview；"
            "开启后 folder worker 只建单收图，等待 edited 回流。"
        ),
    )

    parser.add_argument(
        "--no-telegram",
        action="store_true",
        help="不发送 Telegram 通知。适合本地测试。",
    )

    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default=None,
        help="覆盖 .env 中的 LOG_LEVEL。",
    )

    return parser.parse_args()


def setup_logging(level: str) -> None:
    logger.remove()
    logger.add(
        sys.stderr,
        level=level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "<level>{message}</level>",
    )


def run_once(
    mode: WorkerMode,
    auto_process: bool,
    notify_telegram: bool,
) -> None:
    """
    单次扫描模式。
    """
    logger.info(f"Running worker once. mode={mode}")

    if mode in {"folder", "both"}:
        folder_results = run_folder_watcher(
            once=True,
            auto_process=auto_process,
            notify_telegram=notify_telegram,
        ) or []
        logger.info(f"Folder watcher processed {len(folder_results)} item(s)")
        for result in folder_results:
            if result.success and result.order:
                logger.info(
                    f"OK folder image={result.source_image.filename}, "
                    f"order={result.order.order_id}, status={result.order.status.value}"
                )
            else:
                logger.error(
                    f"FAILED folder image={result.source_image.filename}, error={result.error}"
                )

    if mode in {"edited", "both"}:
        edited_results = run_edited_watcher(
            once=True,
            notify_telegram=notify_telegram,
        ) or []
        logger.info(f"Edited watcher processed {len(edited_results)} item(s)")
        for result in edited_results:
            if result.success:
                logger.info(
                    f"OK edited file={result.edited_file}, "
                    f"order={result.order_id}, image={result.image_id}"
                )
            else:
                logger.error(
                    f"FAILED edited file={result.edited_file}, "
                    f"order={result.order_id}, error={result.error}"
                )


def run_forever(
    mode: WorkerMode,
    auto_process: bool,
    notify_telegram: bool,
) -> None:
    """
    持续监听模式。
    """
    logger.info(f"Running worker forever. mode={mode}")

    if mode == "folder":
        run_folder_watcher(
            once=False,
            auto_process=auto_process,
            notify_telegram=notify_telegram,
        )
        return

    if mode == "edited":
        run_edited_watcher(
            once=False,
            notify_telegram=notify_telegram,
        )
        return

    run_both_forever(
        auto_process=auto_process,
        notify_telegram=notify_telegram,
    )


def run_both_forever(
    auto_process: bool,
    notify_telegram: bool,
) -> None:
    """
    同时运行 folder watcher 和 edited watcher。

    用两个线程分别轮询：
    - folder watcher：监听 data/incoming/
    - edited watcher：监听 data/orders/{order_id}/edited/
    """
    folder_watcher = build_folder_watcher(
        auto_process=auto_process,
        notify_telegram=notify_telegram,
    )
    edited_watcher = build_edited_watcher(
        notify_telegram=notify_telegram,
    )

    folder_thread = threading.Thread(
        target=folder_watcher.run_forever,
        name="folder-watcher",
        daemon=True,
    )
    edited_thread = threading.Thread(
        target=edited_watcher.run_forever,
        name="edited-watcher",
        daemon=True,
    )

    folder_thread.start()
    edited_thread.start()

    logger.info("Both watchers started")

    try:
        while folder_thread.is_alive() and edited_thread.is_alive():
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Stopping watchers...")
        folder_watcher.stop()
        edited_watcher.stop()
        folder_thread.join(timeout=5)
        edited_thread.join(timeout=5)
        logger.info("Both watchers stopped")


def main() -> None:
    args = parse_args()
    settings = get_settings()

    setup_logging(args.log_level or settings.log_level)
    init_db()

    auto_process = not args.no_auto_process
    notify_telegram = not args.no_telegram

    logger.info("Xianyu photo workflow worker")
    logger.info(f"Data directory: {settings.data_dir}")
    logger.info(f"Incoming directory: {settings.incoming_dir}")
    logger.info(f"Orders directory: {settings.orders_dir}")
    logger.info(f"Database path: {settings.database_path}")
    logger.info(f"IMAGE_PROCESSOR_MODE: {settings.image_processor_mode}")
    logger.info(f"with_api auto processing: {auto_process}")

    if args.once:
        run_once(
            mode=args.mode,
            auto_process=auto_process,
            notify_telegram=notify_telegram,
        )
    else:
        run_forever(
            mode=args.mode,
            auto_process=auto_process,
            notify_telegram=notify_telegram,
        )


if __name__ == "__main__":
    main()
