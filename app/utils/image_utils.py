from __future__ import annotations

from pathlib import Path
from typing import Iterable

from PIL import Image, ImageOps


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def is_image_file(path: Path, supported_extensions: Iterable[str] | None = None) -> bool:
    """
    判断路径是否是支持的图片文件。
    """
    extensions = {
        item.lower()
        for item in (supported_extensions or IMAGE_EXTENSIONS)
    }
    return path.is_file() and path.suffix.lower() in extensions


def open_image(path: Path) -> Image.Image:
    """
    安全打开图片，并自动修正 EXIF 方向。

    很多手机照片看起来方向正常，但实际像素方向依赖 EXIF。
    ImageOps.exif_transpose 可以避免后续生成预览图时方向错乱。
    """
    if not path.exists():
        raise FileNotFoundError(f"Image does not exist: {path}")

    image = Image.open(path)
    image = ImageOps.exif_transpose(image)
    return image


def ensure_rgb(image: Image.Image) -> Image.Image:
    """
    转成 RGB。

    JPEG 不支持透明通道，所以保存为 jpg 前需要转 RGB。
    """
    if image.mode == "RGB":
        return image

    if image.mode in {"RGBA", "LA"}:
        background = Image.new("RGB", image.size, (255, 255, 255))
        alpha = image.getchannel("A") if "A" in image.getbands() else None
        background.paste(image.convert("RGBA"), mask=alpha)
        return background

    return image.convert("RGB")


def resize_to_max_side(image: Image.Image, max_side: int) -> Image.Image:
    """
    等比例缩放图片，使最长边不超过 max_side。

    如果原图本身小于 max_side，则返回拷贝，不放大。
    """
    if max_side <= 0:
        raise ValueError("max_side must be greater than 0")

    width, height = image.size
    current_max_side = max(width, height)

    if current_max_side <= max_side:
        return image.copy()

    scale = max_side / current_max_side
    new_size = (
        max(1, int(width * scale)),
        max(1, int(height * scale)),
    )

    return image.resize(new_size, Image.Resampling.LANCZOS)


def save_image(
    image: Image.Image,
    target_path: Path,
    quality: int = 95,
) -> Path:
    """
    根据目标后缀保存图片。

    - .jpg / .jpeg：自动转 RGB
    - .png：保留透明通道
    - .webp：使用 Pillow 默认 webp 支持
    """
    target_path.parent.mkdir(parents=True, exist_ok=True)
    suffix = target_path.suffix.lower()

    if suffix in {".jpg", ".jpeg"}:
        image = ensure_rgb(image)
        image.save(target_path, format="JPEG", quality=quality, optimize=True)
    elif suffix == ".png":
        image.save(target_path, format="PNG", optimize=True)
    elif suffix == ".webp":
        image.save(target_path, format="WEBP", quality=quality, method=6)
    else:
        raise ValueError(f"Unsupported output image format: {suffix}")

    return target_path


def create_preview_image(
    source_path: Path,
    target_path: Path,
    max_side: int = 1600,
    quality: int = 92,
) -> Path:
    """
    从原图生成缩放后的预览图。

    这里只负责缩放和保存，不加水印。
    加水印逻辑放在 app/processors/watermark_processor.py。
    """
    image = open_image(source_path)
    preview = resize_to_max_side(image, max_side=max_side)
    return save_image(preview, target_path, quality=quality)


def get_image_size(path: Path) -> tuple[int, int]:
    """
    获取图片尺寸。
    """
    image = open_image(path)
    return image.size


def get_image_info(path: Path) -> dict[str, object]:
    """
    获取图片基础信息。

    这个函数适合在日志、调试、Telegram 通知中使用。
    """
    image = open_image(path)
    return {
        "path": path.as_posix(),
        "filename": path.name,
        "suffix": path.suffix.lower(),
        "width": image.width,
        "height": image.height,
        "mode": image.mode,
        "size_bytes": path.stat().st_size,
    }


def normalize_image_filename(filename: str, default_suffix: str = ".jpg") -> str:
    """
    标准化图片文件名。

    用于避免用户上传的文件名包含奇怪字符，导致跨平台路径问题。
    """
    raw_path = Path(filename)
    stem = raw_path.stem.strip().replace(" ", "_") or "image"
    suffix = raw_path.suffix.lower() or default_suffix

    if suffix not in IMAGE_EXTENSIONS:
        suffix = default_suffix

    chars: list[str] = []
    for char in stem:
        if char.isalnum() or char in {"_", "-", "."}:
            chars.append(char)
        else:
            chars.append("_")

    safe_stem = "".join(chars).strip("._") or "image"
    return f"{safe_stem}{suffix}"


def convert_to_jpeg(source_path: Path, target_path: Path, quality: int = 95) -> Path:
    """
    把图片转换为 JPEG。

    后续如果你希望所有最终交付图统一成 jpg，可以调用这个函数。
    """
    image = open_image(source_path)
    target_path = target_path.with_suffix(".jpg")
    return save_image(ensure_rgb(image), target_path, quality=quality)
