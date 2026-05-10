from __future__ import annotations

import base64
import mimetypes
from io import BytesIO
from pathlib import Path

from PIL import Image

from config.settings import Settings


def process_image_with_provider(
    input_path: Path,
    output_path: Path,
    prompt: str,
    settings: Settings,
) -> Path:
    provider = settings.api_provider

    if provider == "qwen":
        from services.qwen_client import process_image

        return process_image(
            input_path=input_path,
            output_path=output_path,
            prompt=prompt,
            settings=settings,
        )

    if provider == "openai":
        from services.openai_client import process_image

        return process_image(
            input_path=input_path,
            output_path=output_path,
            prompt=prompt,
            settings=settings,
        )

    if provider in {"gemini", "gemini_flash", "gemini_pro"}:
        from services.gemini_client import process_image

        return process_image(
            input_path=input_path,
            output_path=output_path,
            prompt=prompt,
            settings=settings,
        )

    if provider == "leonardo":
        from services.leonardo_client import process_image

        return process_image(
            input_path=input_path,
            output_path=output_path,
            prompt=prompt,
            settings=settings,
        )

    if provider == "doubao":
        from services.doubao_client import process_image

        return process_image(
            input_path=input_path,
            output_path=output_path,
            prompt=prompt,
            settings=settings,
        )

    raise ValueError(f"Unsupported api_provider: {provider}")


def save_image_reference(
    image_reference: str,
    output_path: Path,
    timeout_seconds: float,
) -> Path:
    if image_reference.startswith(("http://", "https://")):
        import requests

        response = requests.get(image_reference, timeout=timeout_seconds)
        response.raise_for_status()
        image_bytes = response.content
    else:
        image_bytes = _decode_base64_image(image_reference)

    return write_image_bytes(image_bytes, output_path)


def write_image_bytes(image_bytes: bytes, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    suffix = output_path.suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp"}:
        with Image.open(BytesIO(image_bytes)) as image:
            if suffix in {".jpg", ".jpeg"} and image.mode in {"RGBA", "LA", "P"}:
                image = image.convert("RGB")

            if suffix == ".png":
                image.save(output_path, format="PNG")
            elif suffix == ".webp":
                image.save(output_path, format="WEBP", quality=95)
            else:
                image.save(output_path, format="JPEG", quality=95)
    else:
        output_path.write_bytes(image_bytes)

    return output_path


def encode_image_data_url(input_path: Path) -> str:
    if not input_path.exists():
        raise FileNotFoundError(f"Input image does not exist: {input_path}")

    mime_type = mimetypes.guess_type(input_path.name)[0] or "image/jpeg"
    encoded = base64.b64encode(input_path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _decode_base64_image(image_reference: str) -> bytes:
    if "," in image_reference and image_reference.lstrip().startswith("data:"):
        image_reference = image_reference.split(",", maxsplit=1)[1]

    return base64.b64decode(image_reference)
