from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Any

import requests

from config.settings import Settings
from services.image_api_client import save_image_reference


def process_image(
    input_path: Path,
    output_path: Path,
    prompt: str,
    settings: Settings,
) -> Path:
    if not settings.qwen_api_key:
        raise ValueError("QWEN_API_KEY or DASHSCOPE_API_KEY is required for Qwen image processing")

    payload = _build_payload(
        input_path=input_path,
        prompt=prompt,
        settings=settings,
    )
    headers = {
        "Authorization": f"Bearer {settings.qwen_api_key}",
        "Content-Type": "application/json",
    }

    response = requests.post(
        settings.qwen_endpoint,
        headers=headers,
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
    parameters: dict[str, Any] = {
        "n": settings.qwen_image_count,
        "negative_prompt": settings.qwen_negative_prompt,
        "prompt_extend": settings.qwen_prompt_extend,
        "watermark": settings.qwen_watermark,
    }
    if settings.qwen_image_size:
        parameters["size"] = settings.qwen_image_size

    return {
        "model": settings.qwen_image_model,
        "input": {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"image": _encode_image_data_url(input_path)},
                        {"text": prompt},
                    ],
                }
            ]
        },
        "parameters": parameters,
    }


def _encode_image_data_url(input_path: Path) -> str:
    if not input_path.exists():
        raise FileNotFoundError(f"Input image does not exist: {input_path}")

    mime_type = mimetypes.guess_type(input_path.name)[0] or "image/jpeg"
    encoded = base64.b64encode(input_path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _extract_first_image_reference(data: dict[str, Any]) -> str:
    if data.get("code") and data.get("message"):
        raise RuntimeError(f"Qwen API error {data['code']}: {data['message']}")

    try:
        content = data["output"]["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"Qwen API response did not contain image output: {data}") from exc

    for item in content:
        if isinstance(item, dict) and isinstance(item.get("image"), str):
            return item["image"]

    raise RuntimeError(f"Qwen API response did not include an image reference: {data}")
