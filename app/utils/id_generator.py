from __future__ import annotations

import re
import secrets
from datetime import datetime

from config.settings import get_settings


_ORDER_COUNTER_CACHE: dict[str, int] = {}
_IMAGE_COUNTER = 0
_LOG_COUNTER = 0


def _date_prefix() -> str:
    """
    生成订单日期前缀。

    示例：
        ORD_20260508
    """
    return datetime.now().strftime("ORD_%Y%m%d")


def _timestamp_str() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _short_random(length: int = 6) -> str:
    return secrets.token_hex(length // 2 + 1)[:length]


def _extract_order_sequence(order_name: str, date_prefix: str) -> int | None:
    """
    从已有订单目录名中提取当天序号。

    示例：
        order_name = ORD_20260508_3
        date_prefix = ORD_20260508
        返回 3
    """
    pattern = rf"^{re.escape(date_prefix)}_(\d+)$"
    match = re.match(pattern, order_name)

    if not match:
        return None

    return int(match.group(1))


def _get_existing_max_sequence(date_prefix: str) -> int:
    """
    扫描 data/orders/，找出当天已有最大订单序号。

    如果已有：
        ORD_20260508_1
        ORD_20260508_2

    则返回 2，下一个订单就是 ORD_20260508_3。
    """
    settings = get_settings()
    settings.ensure_directories()

    orders_dir = settings.orders_dir
    if not orders_dir.exists():
        return 0

    max_sequence = 0

    for path in orders_dir.iterdir():
        sequence = _extract_order_sequence(path.name, date_prefix)
        if sequence is not None:
            max_sequence = max(max_sequence, sequence)

    return max_sequence


def generate_order_id(prefix: str = "ORD") -> str:
    """
    生成订单 ID。

    示例：
        ORD_20260508_1
        ORD_20260508_2
        ORD_20260508_3

    说明：
    - ORD：订单前缀
    - 20260508：日期
    - 1 / 2 / 3：当天第几个订单
    """
    date_prefix = _date_prefix()

    existing_max = _get_existing_max_sequence(date_prefix)
    cached_max = _ORDER_COUNTER_CACHE.get(date_prefix, 0)

    next_sequence = max(existing_max, cached_max) + 1
    _ORDER_COUNTER_CACHE[date_prefix] = next_sequence

    return f"{date_prefix}_{next_sequence}"


def generate_image_id(order_id: str | None = None, prefix: str = "IMG") -> str:
    """
    生成图片 ID。

    示例：
        ORD_20260508_1_IMG_001_a3f1
    """
    global _IMAGE_COUNTER
    _IMAGE_COUNTER += 1

    if order_id:
        return f"{order_id}_IMG_{_IMAGE_COUNTER:03d}_{_short_random(4)}"

    return f"{prefix}_{_timestamp_str()}_{_IMAGE_COUNTER:04d}_{_short_random()}"


def generate_log_id(prefix: str = "LOG") -> str:
    """
    生成状态日志 ID。
    """
    global _LOG_COUNTER
    _LOG_COUNTER += 1

    return f"{prefix}_{_timestamp_str()}_{_LOG_COUNTER:04d}_{_short_random()}"


def generate_batch_id(prefix: str = "BATCH") -> str:
    """
    生成批次 ID。
    """
    return f"{prefix}_{_timestamp_str()}_{_short_random(8)}"


def generate_safe_token(length: int = 16) -> str:
    """
    生成安全随机 token。
    """
    return secrets.token_urlsafe(length)