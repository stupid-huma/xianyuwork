from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator

from sqlalchemy import DateTime, ForeignKey, String, Text, create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

from app.core.enums import ImageStatus, OrderStatus, SourceType
from app.core.models import Order, OrderImage, OrderStateLog
from config.settings import get_settings


class Base(DeclarativeBase):
    pass


class OrderRow(Base):
    """
    订单表。

    注意：这里是数据库 ORM 模型，不是业务模型。
    业务模型在 app/core/models.py 里。
    """

    __tablename__ = "orders"

    order_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)

    buyer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    buyer_contact: Mapped[str | None] = mapped_column(String(255), nullable=True)
    xianyu_order_id: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)

    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    images: Mapped[list[ImageRow]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class ImageRow(Base):
    """
    图片表。
    """

    __tablename__ = "images"

    image_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    order_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("orders.order_id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)

    original_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    edited_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    preview_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_path: Mapped[str | None] = mapped_column(Text, nullable=True)

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    order: Mapped[OrderRow] = relationship(back_populates="images")


class StateLogRow(Base):
    """
    状态变化日志表。
    """

    __tablename__ = "state_logs"

    log_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    order_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)

    from_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    to_status: Mapped[str] = mapped_column(String(64), nullable=False)
    event: Mapped[str] = mapped_column(String(128), nullable=False)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


def _path_to_str(path: Path | None) -> str | None:
    return path.as_posix() if path else None


def _str_to_path(value: str | None) -> Path | None:
    return Path(value) if value else None


def _safe_json_loads(value: str | None) -> dict:
    if not value:
        return {}
    try:
        result = json.loads(value)
        return result if isinstance(result, dict) else {}
    except json.JSONDecodeError:
        return {}


def get_engine() -> Engine:
    settings = get_settings()
    settings.ensure_directories()

    return create_engine(
        settings.sqlite_url,
        echo=False,
        future=True,
        connect_args={"check_same_thread": False},
    )


engine = get_engine()
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    class_=Session,
)


def init_db() -> None:
    """
    初始化数据库表。

    第一次运行项目前，需要调用一次。
    main.py 里也会调用，确保表存在。
    """
    Base.metadata.create_all(bind=engine)


@contextmanager
def session_scope() -> Iterator[Session]:
    """
    数据库事务上下文。

    用法：
        with session_scope() as session:
            ...
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


class OrderRepository:
    """
    订单仓库层。

    这个类只负责数据库读写，不负责业务状态机判断。
    状态机判断会放在 app/core/order_service.py。
    """

    def save_order(self, order: Order) -> Order:
        """
        新增或更新订单。
        """
        with session_scope() as session:
            row = session.get(OrderRow, order.order_id)

            if row is None:
                row = OrderRow(
                    order_id=order.order_id,
                    status=order.status.value,
                    source_type=order.source_type.value,
                    buyer_name=order.buyer_name,
                    buyer_contact=order.buyer_contact,
                    xianyu_order_id=order.xianyu_order_id,
                    note=order.note,
                    error_message=order.error_message,
                    extra_json=json.dumps(order.extra, ensure_ascii=False),
                    created_at=order.created_at,
                    updated_at=order.updated_at,
                )
                session.add(row)
            else:
                row.status = order.status.value
                row.source_type = order.source_type.value
                row.buyer_name = order.buyer_name
                row.buyer_contact = order.buyer_contact
                row.xianyu_order_id = order.xianyu_order_id
                row.note = order.note
                row.error_message = order.error_message
                row.extra_json = json.dumps(order.extra, ensure_ascii=False)
                row.updated_at = order.updated_at

            existing_images = {image.image_id: image for image in row.images}

            for image in order.images:
                image_row = existing_images.get(image.image_id)

                if image_row is None:
                    image_row = ImageRow(
                        image_id=image.image_id,
                        order_id=order.order_id,
                        filename=image.filename,
                        status=image.status.value,
                        source_type=image.source_type.value,
                        original_path=_path_to_str(image.original_path),
                        edited_path=_path_to_str(image.edited_path),
                        preview_path=_path_to_str(image.preview_path),
                        final_path=_path_to_str(image.final_path),
                        error_message=image.error_message,
                        created_at=image.created_at,
                        updated_at=image.updated_at,
                    )
                    session.add(image_row)
                else:
                    image_row.filename = image.filename
                    image_row.status = image.status.value
                    image_row.source_type = image.source_type.value
                    image_row.original_path = _path_to_str(image.original_path)
                    image_row.edited_path = _path_to_str(image.edited_path)
                    image_row.preview_path = _path_to_str(image.preview_path)
                    image_row.final_path = _path_to_str(image.final_path)
                    image_row.error_message = image.error_message
                    image_row.updated_at = image.updated_at

        return order

    def get_order(self, order_id: str) -> Order | None:
        with session_scope() as session:
            row = session.get(OrderRow, order_id)
            if row is None:
                return None
            return self._row_to_order(row)

    def list_orders(
        self,
        status: OrderStatus | None = None,
        limit: int = 50,
    ) -> list[Order]:
        with session_scope() as session:
            stmt = select(OrderRow).order_by(OrderRow.created_at.desc()).limit(limit)
            if status is not None:
                stmt = stmt.where(OrderRow.status == status.value)

            rows = session.execute(stmt).scalars().all()
            return [self._row_to_order(row) for row in rows]

    def add_state_log(self, log: OrderStateLog) -> None:
        with session_scope() as session:
            row = StateLogRow(
                log_id=log.log_id,
                order_id=log.order_id,
                from_status=log.from_status.value if log.from_status else None,
                to_status=log.to_status.value,
                event=log.event,
                message=log.message,
                created_at=log.created_at,
            )
            session.add(row)

    def list_state_logs(self, order_id: str, limit: int = 100) -> list[OrderStateLog]:
        with session_scope() as session:
            stmt = (
                select(StateLogRow)
                .where(StateLogRow.order_id == order_id)
                .order_by(StateLogRow.created_at.asc())
                .limit(limit)
            )
            rows = session.execute(stmt).scalars().all()
            return [self._row_to_state_log(row) for row in rows]

    def _row_to_order(self, row: OrderRow) -> Order:
        images = [self._row_to_image(image_row) for image_row in row.images]

        return Order(
            order_id=row.order_id,
            status=OrderStatus(row.status),
            source_type=SourceType(row.source_type),
            buyer_name=row.buyer_name,
            buyer_contact=row.buyer_contact,
            xianyu_order_id=row.xianyu_order_id,
            note=row.note,
            images=images,
            error_message=row.error_message,
            extra=_safe_json_loads(row.extra_json),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def _row_to_image(self, row: ImageRow) -> OrderImage:
        return OrderImage(
            image_id=row.image_id,
            order_id=row.order_id,
            filename=row.filename,
            status=ImageStatus(row.status),
            source_type=SourceType(row.source_type),
            original_path=_str_to_path(row.original_path),
            edited_path=_str_to_path(row.edited_path),
            preview_path=_str_to_path(row.preview_path),
            final_path=_str_to_path(row.final_path),
            error_message=row.error_message,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def _row_to_state_log(self, row: StateLogRow) -> OrderStateLog:
        return OrderStateLog(
            log_id=row.log_id,
            order_id=row.order_id,
            from_status=OrderStatus(row.from_status) if row.from_status else None,
            to_status=OrderStatus(row.to_status),
            event=row.event,
            message=row.message,
            created_at=row.created_at,
        )


order_repository = OrderRepository()
