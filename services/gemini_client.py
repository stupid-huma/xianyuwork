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
    if not settings.gemini_api_key:
        raise ValueError("GEMINI_API_KEY is required for Gemini image processing")

    model = _select_model(settings)
    payload = _build_payload(
        input_path=input_path,
        prompt=prompt,
        settings=settings,
    )
    response = requests.post(
        _build_endpoint(settings, model),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": settings.gemini_api_key,
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


def _select_model(settings: Settings) -> str:
    if settings.api_provider == "gemini_flash":
        return settings.gemini_flash_image_model

    if settings.api_provider == "gemini_pro":
        return settings.gemini_pro_image_model

    return settings.gemini_image_model


def _build_endpoint(settings: Settings, model: str) -> str:
    return f"{settings.gemini_endpoint_base_url.rstrip('/')}/{model}:generateContent"


def _build_payload(input_path: Path, prompt: str, settings: Settings) -> dict[str, Any]:
    image_data_url = encode_image_data_url(input_path)
    mime_type, image_data = _split_data_url(image_data_url)

    return {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": mime_type,
                            "data": image_data,
                        }
                    },
                ],
            }
        ],
        "generationConfig": {
            "responseModalities": list(settings.gemini_response_modalities),
        },
    }


def _split_data_url(data_url: str) -> tuple[str, str]:
    prefix, image_data = data_url.split(",", maxsplit=1)
    mime_type = prefix.removeprefix("data:").split(";", maxsplit=1)[0]
    return mime_type, image_data


def _extract_first_image_reference(data: dict[str, Any]) -> str:
    if isinstance(data.get("error"), dict):
        error = data["error"]
        raise RuntimeError(f"Gemini API error: {error.get('message') or error}")

    candidates = data.get("candidates")
    if not isinstance(candidates, list):
        raise RuntimeError(f"Gemini API response did not contain candidates: {data}")

    for candidate in candidates:
        content = candidate.get("content") if isinstance(candidate, dict) else None
        parts = content.get("parts") if isinstance(content, dict) else None
        if not isinstance(parts, list):
            continue

        for part in parts:
            if not isinstance(part, dict):
                continue

            inline_data = part.get("inlineData") or part.get("inline_data")
            if not isinstance(inline_data, dict):
                continue

            image_data = inline_data.get("data")
            if isinstance(image_data, str) and image_data:
                return image_data

    prompt_feedback = data.get("promptFeedback") or data.get("prompt_feedback")
    if prompt_feedback:
        raise RuntimeError(f"Gemini API response had no image output. Prompt feedback: {prompt_feedback}")

    raise RuntimeError(f"Gemini API response did not include image output: {data}")
