from __future__ import annotations

from app.processors.base_image_processor import (
    BaseImageProcessor,
    ImageProcessRequest,
    ImageProcessResult,
)
from config.settings import get_settings
from services.image_api_client import process_image_with_provider


class ApiImageProcessor(BaseImageProcessor):
    """
    Adapter for callers that still use the image processor abstraction.
    OrderService is the main production path for API processing.
    """

    def process(self, request: ImageProcessRequest) -> ImageProcessResult:
        settings = get_settings()
        try:
            output_path = process_image_with_provider(
                input_path=request.input_path,
                output_path=request.output_path,
                prompt=request.prompt or settings.selected_image_prompt,
                settings=settings,
            )
        except Exception as exc:
            return ImageProcessResult(
                success=False,
                error_message=str(exc),
                raw_response={
                    "mode": "api",
                    "provider": settings.api_provider,
                },
            )

        return ImageProcessResult(
            success=True,
            output_path=output_path,
            raw_response={
                "mode": "api",
                "provider": settings.api_provider,
            },
        )
