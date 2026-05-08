from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import ImageStatus, OrderStatus, SourceType


class TimestampMixin(BaseModel):
    """
    通用时间字段。
    """

    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    def touch(self) -> None:
        """
        更新 modified time。
        """
        self.updated_at = datetime.now()


class OrderImage(BaseModel):
    """
    单张图片的业务模型。

    注意：
    - original_path：买家发来的原图
    - edited_path：GPT 或人工处理后的高清图
    - preview_path：加水印后的预览图
    - final_path：最终交付用的无水印高清图
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    image_id: str
    order_id: str
    filename: str

    status: ImageStatus = ImageStatus.RECEIVED
    source_type: SourceType = SourceType.FOLDER

    original_path: Path | None = None
    edited_path: Path | None = None
    preview_path: Path | None = None
    final_path: Path | None = None

    error_message: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    def mark_editing(self) -> None:
        self.status = ImageStatus.EDITING
        self.updated_at = datetime.now()

    def mark_edited(self, edited_path: Path) -> None:
        self.status = ImageStatus.EDITED
        self.edited_path = edited_path
        self.error_message = None
        self.updated_at = datetime.now()

    def mark_preview_generated(self, preview_path: Path) -> None:
        self.status = ImageStatus.PREVIEW_GENERATED
        self.preview_path = preview_path
        self.error_message = None
        self.updated_at = datetime.now()

    def mark_approved(self) -> None:
        self.status = ImageStatus.APPROVED
        self.error_message = None
        self.updated_at = datetime.now()

    def mark_rejected(self, reason: str | None = None) -> None:
        self.status = ImageStatus.REJECTED
        self.error_message = reason
        self.updated_at = datetime.now()

    def mark_final_ready(self, final_path: Path) -> None:
        self.status = ImageStatus.FINAL_READY
        self.final_path = final_path
        self.error_message = None
        self.updated_at = datetime.now()

    def mark_failed(self, error_message: str) -> None:
        self.status = ImageStatus.FAILED
        self.error_message = error_message
        self.updated_at = datetime.now()


class Order(BaseModel):
    """
    订单业务模型。

    一个订单可以对应多张图片。
    当前先适配半自动流程：
    1. 收到图片
    2. 生成处理图
    3. 生成水印预览图
    4. Telegram 审核
    5. 发预览给买家
    6. 买家确认收货后发高清无水印图
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    order_id: str
    status: OrderStatus = OrderStatus.CREATED
    source_type: SourceType = SourceType.FOLDER

    buyer_name: str | None = None
    buyer_contact: str | None = None
    xianyu_order_id: str | None = None

    note: str | None = None
    images: list[OrderImage] = Field(default_factory=list)

    error_message: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)

    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    def touch(self) -> None:
        self.updated_at = datetime.now()

    @property
    def image_count(self) -> int:
        return len(self.images)

    @property
    def has_images(self) -> bool:
        return bool(self.images)

    @property
    def preview_paths(self) -> list[Path]:
        return [image.preview_path for image in self.images if image.preview_path]

    @property
    def final_paths(self) -> list[Path]:
        return [image.final_path for image in self.images if image.final_path]

    def add_image(self, image: OrderImage) -> None:
        self.images.append(image)
        self.touch()

    def set_status(self, status: OrderStatus, error_message: str | None = None) -> None:
        self.status = status
        self.error_message = error_message
        self.touch()

    def mark_failed(self, error_message: str) -> None:
        self.set_status(OrderStatus.FAILED, error_message=error_message)

    def to_metadata_dict(self) -> dict[str, Any]:
        """
        转成适合写入 metadata.json 的字典。

        mode='json' 会把 Path、datetime、Enum 转成 JSON 友好的格式。
        """
        return self.model_dump(mode="json")

    @classmethod
    def from_metadata_dict(cls, data: dict[str, Any]) -> "Order":
        return cls.model_validate(data)


class OrderStateLog(BaseModel):
    """
    订单状态变化日志。

    SQLite 里也会保存一份，方便排查问题。
    """

    log_id: str
    order_id: str
    from_status: OrderStatus | None = None
    to_status: OrderStatus
    event: str
    message: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)


class CreateOrderRequest(BaseModel):
    """
    创建订单时使用的输入模型。
    """

    buyer_name: str | None = None
    buyer_contact: str | None = None
    xianyu_order_id: str | None = None
    source_type: SourceType = SourceType.FOLDER
    note: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class AddImageRequest(BaseModel):
    """
    给订单添加图片时使用的输入模型。
    """

    order_id: str
    source_path: Path
    source_type: SourceType = SourceType.FOLDER
    filename: str | None = None
