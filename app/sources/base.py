from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from app.core.enums import SourceType


@dataclass(frozen=True)
class SourceImage:
    """
    从外部来源发现的一张图片。

    这个结构用于统一不同来源：
    - 本地文件夹
    - 闲鱼监听
    - Telegram
    - QQ
    - 手动上传

    当前阶段主要用于 folder_source.py。
    """

    source_path: Path
    source_type: SourceType
    filename: str

    buyer_name: str | None = None
    buyer_contact: str | None = None
    xianyu_order_id: str | None = None
    note: str | None = None

    extra: dict[str, object] | None = None


class ImageSource(ABC):
    """
    图片来源抽象基类。

    后续如果你接入闲鱼，只需要新增：
        app/sources/xianyu_source.py

    然后实现这个接口即可，不需要大改 order_service / worker。
    """

    source_type: SourceType

    @abstractmethod
    def discover_images(self) -> list[SourceImage]:
        """
        发现待处理图片。

        返回值应该是 SourceImage 列表。
        如果当前没有新图片，返回空列表。
        """
        raise NotImplementedError

    @abstractmethod
    def mark_consumed(self, image: SourceImage) -> None:
        """
        标记图片已经被系统接收。

        对不同来源的含义不同：
        - 文件夹来源：可以移动到 processed 或删除原 incoming 文件
        - 闲鱼来源：可以记录已拉取消息 ID
        - Telegram 来源：可以记录 file_id
        """
        raise NotImplementedError

    def mark_failed(self, image: SourceImage, error: Exception) -> None:
        """
        标记图片处理失败。

        默认不做任何操作。
        子类可以按需重写，例如把文件移动到 failed 目录。
        """
        return None
