from __future__ import annotations

from pathlib import Path
from typing import Any

from openai import OpenAI

from config.settings import Settings
from services.image_api_client import save_image_reference


def process_image(
    input_path: Path,
    output_path: Path,
    prompt: str,
    settings: Settings,
) -> Path:
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is required for OpenAI image processing")

    client = OpenAI(api_key=settings.openai_api_key)

    with input_path.open("rb") as image_file:
        response = client.images.edit(
            model=settings.openai_image_model,
            image=image_file,
            prompt=prompt,
        )

    image_reference = _extract_first_image_reference(response)
    if image_reference:
        return save_image_reference(
            image_reference=image_reference,
            output_path=output_path,
            timeout_seconds=settings.api_request_timeout_seconds,
        )

    image_url = _extract_first_url(response)
    if image_url:
        return save_image_reference(
            image_reference=image_url,
            output_path=output_path,
            timeout_seconds=settings.api_request_timeout_seconds,
        )

    raise RuntimeError(f"OpenAI image response did not contain b64_json or url: {response}")


def _extract_first_image_reference(response: Any) -> str | None:
    image_data = _first_image_data(response)
    if image_data is None:
        return None

    value = _get_value(image_data, "b64_json")
    if isinstance(value, str) and value:
        return value

    # Some SDK versions expose raw bytes on generated image objects.
    value = _get_value(image_data, "bytes")
    if isinstance(value, bytes):
        return _write_bytes_to_temp_reference(value)

    return None


def _extract_first_url(response: Any) -> str | None:
    image_data = _first_image_data(response)
    if image_data is None:
        return None

    value = _get_value(image_data, "url")
    if isinstance(value, str) and value.startswith(("http://", "https://")):
        return value

    return None


def _first_image_data(response: Any) -> Any | None:
    data = _get_value(response, "data")
    if isinstance(data, list) and data:
        return data[0]
    return None


def _get_value(obj: Any, key: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def _write_bytes_to_temp_reference(image_bytes: bytes) -> str:
    # Keep bytes support out of the main path; current GPT image models return base64.
    import base64

    return base64.b64encode(image_bytes).decode("ascii")
