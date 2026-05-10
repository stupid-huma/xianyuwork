from __future__ import annotations

import shutil
from pathlib import Path

from PIL import Image, ImageDraw
from loguru import logger

from app.core.enums import OrderStatus, ReviewDecision
from app.core.order_service import order_service
from app.storage.database import init_db
from app.workers.edited_watcher import run_edited_watcher
from config.paths import get_project_paths
from config.settings import get_settings


TEST_IMAGE_NAME = "smoke_test_input.jpg"


def create_test_image(path: Path) -> Path:
    """
    创建一张测试图片。

    这个测试不依赖外部图片，方便第一次部署时直接验证项目是否可运行。
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    image = Image.new("RGB", (1200, 800), (235, 235, 235))
    draw = ImageDraw.Draw(image)

    draw.rectangle((80, 80, 1120, 720), outline=(80, 80, 80), width=6)
    draw.text((120, 120), "Xianyu Photo Workflow", fill=(20, 20, 20))
    draw.text((120, 180), "Smoke Test Image", fill=(20, 20, 20))
    draw.text((120, 240), "Local edited watcher pipeline", fill=(20, 20, 20))

    image.save(path, format="JPEG", quality=95)
    return path


def cleanup_previous_test_input() -> None:
    """
    只清理 incoming 里的测试图片，不删除数据库历史。
    """
    settings = get_settings()
    test_image = settings.incoming_dir / TEST_IMAGE_NAME
    if test_image.exists():
        test_image.unlink()


def assert_file_exists(path: Path | None, label: str) -> None:
    if path is None:
        raise AssertionError(f"{label} path is None")

    if not path.exists():
        raise AssertionError(f"{label} file does not exist: {path}")


def assert_path_cleared(path: Path | None, label: str) -> None:
    if path is not None:
        raise AssertionError(f"Expected {label} path to be cleared, got: {path}")


def copy_manual_edited_image(order_id: str, source_path: Path, filename: str) -> Path:
    """
    模拟人工修图完成：把成图放入 data/orders/{order_id}/edited/。
    """
    paths = get_project_paths()
    edited_path = paths.build_edited_image_path(order_id, filename)
    edited_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, edited_path)
    return edited_path


def run_edited_watcher_once(order_id: str) -> None:
    results = run_edited_watcher(once=True, notify_telegram=False) or []
    if not any(result.success and result.order_id == order_id for result in results):
        details = ", ".join(
            f"{result.order_id}:{result.success}:{result.error}" for result in results
        )
        raise AssertionError(f"Expected edited watcher to process {order_id}. Results: {details}")


def run_smoke_test() -> None:
    settings = get_settings()
    paths = get_project_paths()
    init_db()
    cleanup_previous_test_input()

    logger.info("Starting smoke test")
    logger.info(f"Data directory: {settings.data_dir}")
    logger.info(f"Incoming directory: {settings.incoming_dir}")
    logger.info(f"Orders directory: {settings.orders_dir}")
    logger.info(f"Database path: {settings.database_path}")
    logger.info(f"image_processor_mode: {settings.image_processor_mode}")

    source_image = create_test_image(settings.incoming_dir / TEST_IMAGE_NAME)
    logger.info(f"Created test image: {source_image}")

    order = order_service.create_order_with_image(
        source_path=source_image,
        buyer_name="Smoke Test Buyer",
        note="Created by smoke_test.py",
        extra={"test": True},
    )

    if order.status != OrderStatus.IMAGES_RECEIVED:
        raise AssertionError(f"Expected IMAGES_RECEIVED, got {order.status}")

    order = order_service.wait_for_edited(order.order_id)
    if order.status != OrderStatus.WAITING_FOR_EDITED:
        raise AssertionError(f"Expected WAITING_FOR_EDITED, got {order.status}")

    if order.image_count != 1:
        raise AssertionError(f"Expected 1 image, got {order.image_count}")

    image = order.images[0]
    assert_file_exists(image.original_path, "original")
    assert_path_cleared(image.edited_path, "edited")
    assert_path_cleared(image.preview_path, "preview")
    logger.info(f"Original image copied: {image.original_path}")

    edited_path = copy_manual_edited_image(
        order_id=order.order_id,
        source_path=image.original_path,
        filename=image.filename,
    )
    logger.info(f"Manual edited image placed: {edited_path}")

    run_edited_watcher_once(order.order_id)
    order = order_service.get_order(order.order_id)

    if order.status != OrderStatus.WAITING_FOR_REVIEW:
        raise AssertionError(f"Expected WAITING_FOR_REVIEW, got {order.status}")

    image = order.images[0]
    first_edited_path = image.edited_path
    first_preview_path = image.preview_path
    assert_file_exists(first_edited_path, "edited")
    assert_file_exists(first_preview_path, "preview")
    logger.info(f"Preview generated: {first_preview_path}")

    order = order_service.review_order(
        order_id=order.order_id,
        decision=ReviewDecision.REJECT,
        message="Smoke test rework",
    )

    if order.status != OrderStatus.REWORK_REQUIRED:
        raise AssertionError(f"Expected REWORK_REQUIRED after reject, got {order.status}")

    image = order.images[0]
    assert_path_cleared(image.edited_path, "edited")
    assert_path_cleared(image.preview_path, "preview")
    assert_path_cleared(image.final_path, "final")

    if first_edited_path is not None and first_edited_path.exists():
        raise AssertionError(f"Rejected edited file was not archived: {first_edited_path}")

    if first_preview_path is not None and first_preview_path.exists():
        raise AssertionError(f"Rejected preview file was not archived: {first_preview_path}")

    rejected_files = list(paths.rejected_dir(order.order_id).glob("*"))
    if len(rejected_files) < 2:
        raise AssertionError("Expected rejected archive to contain old edited and preview files")

    logger.info(f"Rejected files archived: {paths.rejected_dir(order.order_id)}")

    rework_edited_path = copy_manual_edited_image(
        order_id=order.order_id,
        source_path=image.original_path,
        filename=image.filename,
    )
    logger.info(f"Reworked edited image placed: {rework_edited_path}")

    run_edited_watcher_once(order.order_id)
    order = order_service.get_order(order.order_id)

    if order.status != OrderStatus.WAITING_FOR_REVIEW:
        raise AssertionError(f"Expected WAITING_FOR_REVIEW after rework, got {order.status}")

    image = order.images[0]
    assert_file_exists(image.edited_path, "reworked edited")
    assert_file_exists(image.preview_path, "reworked preview")

    order = order_service.review_order(
        order_id=order.order_id,
        decision=ReviewDecision.APPROVE,
        message="Smoke test approve",
    )

    if order.status != OrderStatus.REVIEW_APPROVED:
        raise AssertionError(f"Expected REVIEW_APPROVED after approve, got {order.status}")

    order = order_service.mark_preview_sent(order.order_id)

    if order.status != OrderStatus.PREVIEW_SENT:
        raise AssertionError(f"Expected PREVIEW_SENT, got {order.status}")

    order = order_service.mark_buyer_confirmed(order.order_id)

    if order.status != OrderStatus.BUYER_CONFIRMED:
        raise AssertionError(f"Expected BUYER_CONFIRMED, got {order.status}")

    order = order_service.mark_final_sent(order.order_id)

    if order.status != OrderStatus.FINAL_SENT:
        raise AssertionError(f"Expected FINAL_SENT, got {order.status}")

    image = order.images[0]
    assert_file_exists(image.final_path, "final")
    logger.info(f"Final image ready: {image.final_path}")

    order = order_service.complete_order(order.order_id)

    if order.status != OrderStatus.COMPLETED:
        raise AssertionError(f"Expected COMPLETED, got {order.status}")

    logs = order_service.list_state_logs(order.order_id)
    if not logs:
        raise AssertionError("Expected state logs, got empty list")

    print()
    print("Smoke test passed")
    print()
    print(f"Order ID: {order.order_id}")
    print(f"Final status: {order.status.value}")
    print(f"Original: {image.original_path}")
    print(f"Edited:   {image.edited_path}")
    print(f"Preview:  {image.preview_path}")
    print(f"Final:    {image.final_path}")
    print(f"Rejected: {paths.rejected_dir(order.order_id)}")
    print(f"State logs: {len(logs)}")
    print()
    print("Next recommended test:")
    print("  python run_worker.py --once --no-telegram")
    print("  python run_worker.py --mode edited --once --no-telegram")
    print()


if __name__ == "__main__":
    run_smoke_test()
