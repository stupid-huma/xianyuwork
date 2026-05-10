from __future__ import annotations

from pathlib import Path
from typing import Any

import requests

from config.settings import Settings
from services.image_api_client import encode_image_data_url, save_image_reference


def process_image(
    input_path: Path,
    output_path: Path,
    prompt: str,
    settings: Settings,
) -> Path:
    if not settings.doubao_api_key:
        raise ValueError("DOUBAO_API_KEY or ARK_API_KEY is required for Doubao image processing")

    payload = _build_payload(
        input_path=input_path,
        prompt=prompt,
        settings=settings,
    )
    response = requests.post(
        _api_url(settings, "images/generations"),
        headers={
            "Authorization": f"Bearer {settings.doubao_api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=settings.api_request_timeout_seconds,
    )
    response.raise_for_status()
    data = response.json()

    image_reference = _extract_first_image_reference(data)
    return save_image_reference(
        image_reference=image_reference,
        output_path=output_path,
        timeout_seconds=settings.api_request_timeout_seconds,
    )


def _build_payload(input_path: Path, prompt: str, settings: Settings) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": settings.doubao_image_model,
        "prompt": prompt,
        "image": encode_image_data_url(input_path),
        "response_format": settings.doubao_response_format,
        "size": settings.doubao_size,
        "watermark": settings.doubao_watermark,
    }

    if settings.doubao_seed is not None:
        payload["seed"] = settings.doubao_seed

    if settings.doubao_guidance_scale is not None:
        payload["guidance_scale"] = settings.doubao_guidance_scale

    return payload


def _api_url(settings: Settings, path: str) -> str:
    return f"{settings.doubao_api_base_url.rstrip('/')}/{path.lstrip('/')}"


def _extract_first_image_reference(data: dict[str, Any]) -> str:
    error = data.get("error")
    if isinstance(error, dict):
        raise RuntimeError(f"Doubao API error: {error.get('message') or error}")

    if data.get("code") and data.get("message"):
        raise RuntimeError(f"Doubao API error {data['code']}: {data['message']}")

    image_reference = _extract_from_openai_style_data(data)
    if image_reference:
        return image_reference

    image_reference = _extract_from_common_image_lists(data)
    if image_reference:
        return image_reference

    raise RuntimeError(f"Doubao API response did not include image output: {data}")


def _extract_from_openai_style_data(data: dict[str, Any]) -> str | None:
    images = data.get("data")
    if not isinstance(images, list):
        return None

    for image in images:
        if not isinstance(image, dict):
            continue

        for key in ("b64_json", "url"):
            image_reference = image.get(key)
            if isinstance(image_reference, str) and image_reference:
                return image_reference

    return None


def _extract_from_common_image_lists(data: dict[str, Any]) -> str | None:
    for key in ("images", "image_urls", "urls"):
        images = data.get(key)
        if not isinstance(images, list):
            continue

        for image in images:
            if isinstance(image, str) and image:
                return image

            if isinstance(image, dict):
                for image_key in ("b64_json", "url", "image_url"):
                    image_reference = image.get(image_key)
                    if isinstance(image_reference, str) and image_reference:
                        return image_reference

    return None
