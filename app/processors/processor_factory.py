from __future__ import annotations

from app.processors.base_image_processor import BaseImageProcessor
from app.processors.local_copy_processor import LocalCopyImageProcessor
from app.processors.with_api_processor import WithApiImageProcessor
from config.settings import get_settings


def build_image_processor(mode: str | None = None) -> BaseImageProcessor:
    settings = get_settings()
    selected_mode = mode or settings.image_processor_mode

    if selected_mode == "local":
        return LocalCopyImageProcessor()

    if selected_mode == "with_api":
        return WithApiImageProcessor()

    raise ValueError(f"Unsupported image processor mode: {selected_mode}")