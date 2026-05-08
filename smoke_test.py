from __future__ import annotations

import shutil
from pathlib import Path

from PIL import Image, ImageDraw
from loguru import logger

from app.core.enums import OrderStatus, ReviewDecision
from app.core.order_service import order_service
from app.storage.database import init_db
from config.settings import get_settings


TEST_IMAGE_NAME = "smoke_test_input.jpg"


def create_test_image(path: Path) -> Path:
    """
    创建一张测试图片。

    这个测试不依赖外部图片，方便你第一次部署时直接验证项目是否可运行。
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    image = Image.new("RGB", (1200, 800), (235, 235, 235))
    draw = ImageDraw.Draw(image)

    draw.rectangle((80, 80, 1120, 720), outline=(80, 80, 80), width=6)
    draw.text((120, 120), "Xianyu Photo Workflow", fill=(20, 20, 20))
    draw.text((120, 180), "Smoke Test Image", fill=(20, 20, 20))
    draw.text((120, 240), "If preview is generated, pipeline works.", fill=(20, 20, 20))

    image.save(path, format="JPEG", quality=95)
    return path


def cleanup_previous_test_orders() -> None:
    """
    可选清理：只清理 incoming 里的测试图片，不删除数据库历史。

    数据库里的历史 smoke test 订单保留，方便你观察状态日志。
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


def run_smoke_test() -> None:
    settings = get_settings()
    init_db()
    cleanup_previous_test_orders()

    logger.info("Starting smoke test")
    logger.info(f"Data directory: {settings.data_dir}")
    logger.info(f"Incoming directory: {settings.incoming_dir}")
    logger.info(f"Orders directory: {settings.orders_dir}")
    logger.info(f"Database path: {settings.database_path}")

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

    if order.image_count != 1:
        raise AssertionError(f"Expected 1 image, got {order.image_count}")

    image = order.images[0]
    assert_file_exists(image.original_path, "original")
    logger.info(f"Original image copied: {image.original_path}")

    order = order_service.process_order_without_ai(order.order_id)

    if order.status != OrderStatus.WAITING_FOR_REVIEW:
        raise AssertionError(f"Expected WAITING_FOR_REVIEW, got {order.status}")

    image = order.images[0]
    assert_file_exists(image.edited_path, "edited")
    assert_file_exists(image.preview_path, "preview")
    logger.info(f"Edited image ready: {image.edited_path}")
    logger.info(f"Preview image generated: {image.preview_path}")

    order = order_service.review_order(
        order_id=order.order_id,
        decision=ReviewDecision.APPROVE,
        message="Smoke test approve",
    )

    if order.status != OrderStatus.PREVIEW_SENT:
        raise AssertionError(f"Expected PREVIEW_SENT after approve, got {order.status}")

    order = order_service.mark_preview_sent(order.order_id)

    if order.status != OrderStatus.WAITING_FOR_BUYER_CONFIRM:
        raise AssertionError(f"Expected WAITING_FOR_BUYER_CONFIRM, got {order.status}")

    order = order_service.mark_buyer_confirmed(order.order_id)

    if order.status != OrderStatus.WAITING_FOR_BUYER_CONFIRM:
        raise AssertionError(f"Expected WAITING_FOR_BUYER_CONFIRM, got {order.status}")

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
    print("✅ Smoke test passed")
    print()
    print(f"Order ID: {order.order_id}")
    print(f"Final status: {order.status.value}")
    print(f"Original: {image.original_path}")
    print(f"Edited:   {image.edited_path}")
    print(f"Preview:  {image.preview_path}")
    print(f"Final:    {image.final_path}")
    print(f"State logs: {len(logs)}")
    print()
    print("Next recommended test:")
    print("  python run_worker.py --once --no-telegram")
    print()


if __name__ == "__main__":
    run_smoke_test()
