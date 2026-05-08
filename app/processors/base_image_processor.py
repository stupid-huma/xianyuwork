from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ImageProcessRequest:
    order_id: str
    image_id: str
    input_path: Path
    output_path: Path
    filename: str
    prompt: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ImageProcessResult:
    success: bool
    output_path: Path | None = None
    error_message: str | None = None
    raw_response: dict[str, Any] | None = None


class BaseImageProcessor(ABC):
    @abstractmethod
    def process(self, request: ImageProcessRequest) -> ImageProcessResult:
        raise NotImplementedError