from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.utils.image_utils import open_image, resize_to_max_side, save_image
from config.paths import ProjectPaths, get_project_paths
from config.settings import get_settings


class WatermarkProcessor:
    """
    水印预览图处理器。

    职责：
    - 从高清图生成缩放预览图
    - 给预览图添加水印
    - 输出到订单 preview 目录

    注意：
    - 这里只做本地图片处理
    - 不负责 GPT 修图
    - 不负责 Telegram 发送
    - 不负责订单状态切换
    """

    def __init__(self, paths: ProjectPaths | None = None) -> None:
        self.settings = get_settings()
        self.paths = paths or get_project_paths()

    def generate_preview_with_watermark(
        self,
        order_id: str,
        source_path: Path,
        output_filename: str | None = None,
        watermark_text: str | None = None,
    ) -> Path:
        """
        从 source_path 生成带水印预览图。

        参数：
            order_id: 订单 ID
            source_path: 通常是 edited 目录里的高清处理图
            output_filename: 可选输出文件名
            watermark_text: 可选水印文字，不传则读取 .env 中 WATERMARK_TEXT

        返回：
            预览图路径
        """
        if not source_path.exists():
            raise FileNotFoundError(f"Source image does not exist: {source_path}")

        self.paths.ensure_order_dirs(order_id)

        filename = output_filename or source_path.name
        output_path = self.paths.build_preview_image_path(order_id, filename)
        output_path = self._avoid_overwrite(output_path)

        image = open_image(source_path)
        preview = resize_to_max_side(image, max_side=self.settings.preview_max_size)

        watermarked = self.add_repeated_diagonal_watermark(
            preview,
            text=watermark_text or self.settings.watermark_text,
            opacity=self.settings.watermark_opacity,
        )

        return save_image(watermarked, output_path, quality=92)

    def add_repeated_diagonal_watermark(
        self,
        image: Image.Image,
        text: str,
        opacity: int = 90,
        angle: float = -30,
    ) -> Image.Image:
        """
        添加重复斜向水印。

        这种水印适合闲鱼预览图：
        - 不太遮挡整体观感
        - 但也不容易被简单裁剪去掉
        """
        if not text.strip():
            return image.copy()

        opacity = max(0, min(255, opacity))

        base = image.convert("RGBA")
        width, height = base.size

        font_size = self._calculate_font_size(width, height)
        font = self._load_font(font_size)

        tile_width = max(360, int(width * 0.45))
        tile_height = max(220, int(height * 0.28))

        tile = Image.new("RGBA", (tile_width, tile_height), (255, 255, 255, 0))
        draw = ImageDraw.Draw(tile)

        text_bbox = draw.textbbox((0, 0), text, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]

        text_x = max(0, (tile_width - text_width) // 2)
        text_y = max(0, (tile_height - text_height) // 2)

        draw.text(
            (text_x, text_y),
            text,
            font=font,
            fill=(255, 255, 255, opacity),
            stroke_width=max(1, font_size // 20),
            stroke_fill=(0, 0, 0, max(0, opacity // 2)),
        )

        rotated_tile = tile.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC)
        watermark_layer = Image.new("RGBA", base.size, (255, 255, 255, 0))

        rotated_width, rotated_height = rotated_tile.size
        x_start = -rotated_width
        y_start = -rotated_height

        for y in range(y_start, height + rotated_height, rotated_height):
            for x in range(x_start, width + rotated_width, rotated_width):
                watermark_layer.alpha_composite(rotated_tile, (x, y))

        result = Image.alpha_composite(base, watermark_layer)

        if image.mode == "RGBA":
            return result

        return result.convert("RGB")

    def add_center_watermark(
        self,
        image: Image.Image,
        text: str,
        opacity: int = 110,
    ) -> Image.Image:
        """
        添加居中水印。

        当前主流程默认不用它，但保留给后续手动生成强水印预览图。
        """
        if not text.strip():
            return image.copy()

        opacity = max(0, min(255, opacity))

        base = image.convert("RGBA")
        width, height = base.size
        font_size = self._calculate_font_size(width, height, ratio=0.07)
        font = self._load_font(font_size)

        layer = Image.new("RGBA", base.size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(layer)

        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        x = (width - text_width) // 2
        y = (height - text_height) // 2

        stroke_width = max(2, font_size // 18)
        draw.text(
            (x, y),
            text,
            font=font,
            fill=(255, 255, 255, opacity),
            stroke_width=stroke_width,
            stroke_fill=(0, 0, 0, max(0, opacity // 2)),
        )

        result = Image.alpha_composite(base, layer)

        if image.mode == "RGBA":
            return result

        return result.convert("RGB")

    def _calculate_font_size(
        self,
        width: int,
        height: int,
        ratio: float = 0.045,
    ) -> int:
        """
        根据图片尺寸计算水印字号。
        """
        diagonal = math.sqrt(width * width + height * height)
        return max(24, min(96, int(diagonal * ratio)))

    def _load_font(self, font_size: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
        """
        加载字体。

        优先使用常见系统字体；找不到就退回 Pillow 默认字体。
        Windows / macOS / Linux 都尽量兼容。
        """
        font_candidates = [
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/msyh.ttc",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/System/Library/Fonts/PingFang.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        ]

        for font_path in font_candidates:
            path = Path(font_path)
            if path.exists():
                try:
                    return ImageFont.truetype(path.as_posix(), font_size)
                except OSError:
                    continue

        return ImageFont.load_default()

    def _avoid_overwrite(self, target_path: Path) -> Path:
        """
        避免覆盖已有预览图。
        """
        if not target_path.exists():
            return target_path

        parent = target_path.parent
        stem = target_path.stem
        suffix = target_path.suffix

        index = 1
        while True:
            candidate = parent / f"{stem}_{index:03d}{suffix}"
            if not candidate.exists():
                return candidate
            index += 1


watermark_processor = WatermarkProcessor()
