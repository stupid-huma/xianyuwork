from __future__ import annotations

import json
import mimetypes
import time
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
    if not settings.leonardo_api_key:
        raise ValueError("LEONARDO_API_KEY is required for Leonardo image processing")

    session = requests.Session()
    init_image_id = _upload_init_image(
        session=session,
        input_path=input_path,
        settings=settings,
    )
    generation_id = _create_generation(
        session=session,
        init_image_id=init_image_id,
        prompt=prompt,
        settings=settings,
    )
    generation_data = _wait_for_generation(
        session=session,
        generation_id=generation_id,
        settings=settings,
    )
    image_reference = _extract_first_image_reference(generation_data)

    return save_image_reference(
        image_reference=image_reference,
        output_path=output_path,
        timeout_seconds=settings.api_request_timeout_seconds,
    )


def _upload_init_image(
    session: requests.Session,
    input_path: Path,
    settings: Settings,
) -> str:
    extension = input_path.suffix.lower().lstrip(".")
    if extension == "jpg":
        extension = "jpeg"

    if extension not in {"jpeg", "png", "webp"}:
        raise ValueError("Leonardo init images must be jpg, jpeg, png, or webp")

    response = session.post(
        _api_url(settings, "init-image"),
        headers=_api_headers(settings),
        json={"extension": extension},
        timeout=settings.api_request_timeout_seconds,
    )
    response.raise_for_status()
    upload_data = response.json()
    upload_info = _extract_upload_info(upload_data)

    mime_type = mimetypes.guess_type(input_path.name)[0] or f"image/{extension}"
    with input_path.open("rb") as image_file:
        upload_response = requests.post(
            upload_info["url"],
            data=upload_info["fields"],
            files={"file": (input_path.name, image_file, mime_type)},
            timeout=settings.api_request_timeout_seconds,
        )
    upload_response.raise_for_status()

    return upload_info["id"]


def _create_generation(
    session: requests.Session,
    init_image_id: str,
    prompt: str,
    settings: Settings,
) -> str:
    payload: dict[str, Any] = {
        "prompt": prompt,
        "modelId": settings.leonardo_model_id,
        "width": settings.leonardo_width,
        "height": settings.leonardo_height,
        "num_images": settings.leonardo_num_images,
        "alchemy": settings.leonardo_alchemy,
        "init_image_id": init_image_id,
        "init_strength": settings.leonardo_init_strength,
        "isInitImage": True,
    }
    if settings.leonardo_preset_style:
        payload["presetStyle"] = settings.leonardo_preset_style

    response = session.post(
        _api_url(settings, "generations"),
        headers=_api_headers(settings),
        json=payload,
        timeout=settings.api_request_timeout_seconds,
    )
    response.raise_for_status()
    data = response.json()

    generation_id = _get_nested(data, ("sdGenerationJob", "generationId"))
    if not isinstance(generation_id, str):
        generation_id = _get_nested(data, ("generationId",))

    if not isinstance(generation_id, str) or not generation_id:
        raise RuntimeError(f"Leonardo response did not contain generationId: {data}")

    return generation_id


def _wait_for_generation(
    session: requests.Session,
    generation_id: str,
    settings: Settings,
) -> dict[str, Any]:
    for _ in range(settings.leonardo_max_poll_attempts):
        response = session.get(
            _api_url(settings, f"generations/{generation_id}"),
            headers=_api_headers(settings),
            timeout=settings.api_request_timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()

        if _safe_extract_first_image_reference(data):
            return data

        status = _extract_generation_status(data)
        if status in {"FAILED", "ERROR", "CANCELED", "CANCELLED"}:
            raise RuntimeError(f"Leonardo generation failed with status={status}: {data}")

        time.sleep(settings.leonardo_poll_interval_seconds)

    raise TimeoutError(f"Timed out waiting for Leonardo generation: {generation_id}")


def _api_url(settings: Settings, path: str) -> str:
    return f"{settings.leonardo_api_base_url.rstrip('/')}/{path.lstrip('/')}"


def _api_headers(settings: Settings) -> dict[str, str]:
    return {
        "accept": "application/json",
        "authorization": f"Bearer {settings.leonardo_api_key}",
        "content-type": "application/json",
    }


def _extract_upload_info(data: dict[str, Any]) -> dict[str, Any]:
    upload = data.get("uploadInitImage")
    if not isinstance(upload, dict):
        upload = data.get("initImage")
    if not isinstance(upload, dict):
        upload = data

    image_id = upload.get("id")
    url = upload.get("url")
    fields = upload.get("fields")

    if isinstance(fields, str):
        fields = json.loads(fields)

    if not isinstance(image_id, str) or not image_id:
        raise RuntimeError(f"Leonardo upload response did not contain init image id: {data}")

    if not isinstance(url, str) or not url:
        raise RuntimeError(f"Leonardo upload response did not contain presigned url: {data}")

    if not isinstance(fields, dict):
        raise RuntimeError(f"Leonardo upload response did not contain presigned fields: {data}")

    return {
        "id": image_id,
        "url": url,
        "fields": fields,
    }


def _extract_generation_status(data: dict[str, Any]) -> str | None:
    generation = _extract_generation_container(data)
    status = generation.get("status") if isinstance(generation, dict) else None
    return status.upper() if isinstance(status, str) else None


def _extract_first_image_reference(data: dict[str, Any]) -> str:
    image_reference = _safe_extract_first_image_reference(data)
    if image_reference:
        return image_reference

    raise RuntimeError(f"Leonardo generation response did not include generated image url: {data}")


def _safe_extract_first_image_reference(data: dict[str, Any]) -> str | None:
    generation = _extract_generation_container(data)
    containers = [generation, data]

    for container in containers:
        if not isinstance(container, dict):
            continue

        for key in ("generated_images", "generatedImages", "images"):
            images = container.get(key)
            if not isinstance(images, list):
                continue

            for image in images:
                if not isinstance(image, dict):
                    continue

                for url_key in ("url", "imageUrl", "image_url"):
                    image_url = image.get(url_key)
                    if isinstance(image_url, str) and image_url:
                        return image_url

    return None


def _extract_generation_container(data: dict[str, Any]) -> dict[str, Any] | None:
    for key in ("generations_by_pk", "generation", "generationById"):
        value = data.get(key)
        if isinstance(value, dict):
            return value

    return data


def _get_nested(data: dict[str, Any], path: tuple[str, ...]) -> Any:
    value: Any = data
    for key in path:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value
