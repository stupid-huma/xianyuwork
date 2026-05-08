from __future__ import annotations

import shutil

from app.processors.base_image_processor import (
    BaseImageProcessor,
    ImageProcessRequest,
    ImageProcessResult,
)


class LocalCopyImageProcessor(BaseImageProcessor):
    """
    本地占位处理器：
    直接把原图复制到 edited 路径，模拟“处理完成”的结果。
    """

    def process(self, request: ImageProcessRequest) -> ImageProcessResult:
        try:
            request.output_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(request.input_path, request.output_path)

            return ImageProcessResult(
                success=True,
                output_path=request.output_path,
                raw_response={
                    "mode": "local",
                    "message": "Copied original image as edited output",
                },
            )
        except Exception as exc:
            return ImageProcessResult(
                success=False,
                error_message=str(exc),
            )