from __future__ import annotations

from app.processors.base_image_processor import (
    BaseImageProcessor,
    ImageProcessRequest,
    ImageProcessResult,
)


class WithApiImageProcessor(BaseImageProcessor):
    """
    预留给后续 API 图像处理。
    当前先不真正调用 API，只返回失败提示。
    """

    def process(self, request: ImageProcessRequest) -> ImageProcessResult:
        return ImageProcessResult(
            success=False,
            error_message=(
                "with_api processor is reserved but not implemented yet. "
                "You can implement OpenAI API or another image backend here later."
            ),
            raw_response={"mode": "with_api"},
        )