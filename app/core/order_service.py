from __future__ import annotations

from pathlib import Path

from app.core.enums import ImageStatus, OrderEvent, OrderStatus, ReviewDecision, SourceType
from app.core.models import AddImageRequest, CreateOrderRequest, Order, OrderImage, OrderStateLog
from app.processors.watermark_processor import WatermarkProcessor, watermark_processor
from app.storage.database import OrderRepository, order_repository
from app.storage.file_store import FileStore, file_store
from app.utils.id_generator import generate_image_id, generate_log_id, generate_order_id
from config.paths import ProjectPaths, get_project_paths
from config.settings import get_settings


class InvalidOrderTransitionError(RuntimeError):
    """
    非法订单状态流转。
    """


class OrderNotFoundError(RuntimeError):
    """
    订单不存在。
    """


class OrderService:
    """
    订单状态机服务。

    当前版本核心规则：
    1. original 只保存买家原图
    2. edited 只保存真正处理完成的图片
       - local 模式：人工放入 edited
       - with_api 模式：API 输出到 edited
    3. preview 只能从 edited 生成
    """

    TRANSITIONS: dict[OrderEvent, tuple[set[OrderStatus] | None, OrderStatus]] = {
        OrderEvent.CREATE_ORDER: (None, OrderStatus.CREATED),
        OrderEvent.REQUEST_IMAGES: (
            {OrderStatus.CREATED},
            OrderStatus.WAITING_FOR_IMAGES,
        ),
        OrderEvent.RECEIVE_IMAGES: (
            {OrderStatus.CREATED, OrderStatus.WAITING_FOR_IMAGES, OrderStatus.IMAGES_RECEIVED},
            OrderStatus.IMAGES_RECEIVED,
        ),
        OrderEvent.START_PROCESSING: (
            {OrderStatus.IMAGES_RECEIVED, OrderStatus.FAILED},
            OrderStatus.PROCESSING,
        ),
        OrderEvent.FINISH_PROCESSING: (
            {OrderStatus.PROCESSING},
            OrderStatus.WAITING_FOR_REVIEW,
        ),
        OrderEvent.SUBMIT_REVIEW: (
            {OrderStatus.PROCESSING, OrderStatus.WAITING_FOR_REVIEW},
            OrderStatus.WAITING_FOR_REVIEW,
        ),
        OrderEvent.APPROVE_REVIEW: (
            {OrderStatus.WAITING_FOR_REVIEW},
            OrderStatus.PREVIEW_SENT,
        ),
        OrderEvent.REJECT_REVIEW: (
            {OrderStatus.WAITING_FOR_REVIEW},
            OrderStatus.PROCESSING,
        ),
        OrderEvent.SEND_PREVIEW: (
            {OrderStatus.WAITING_FOR_REVIEW, OrderStatus.PREVIEW_SENT},
            OrderStatus.WAITING_FOR_BUYER_CONFIRM,
        ),
        OrderEvent.BUYER_CONFIRMED: (
            {OrderStatus.PREVIEW_SENT, OrderStatus.WAITING_FOR_BUYER_CONFIRM},
            OrderStatus.WAITING_FOR_BUYER_CONFIRM,
        ),
        OrderEvent.SEND_FINAL: (
            {OrderStatus.WAITING_FOR_BUYER_CONFIRM},
            OrderStatus.FINAL_SENT,
        ),
        OrderEvent.COMPLETE_ORDER: (
            {OrderStatus.FINAL_SENT},
            OrderStatus.COMPLETED,
        ),
        OrderEvent.CANCEL_ORDER: (
            {
                OrderStatus.CREATED,
                OrderStatus.WAITING_FOR_IMAGES,
                OrderStatus.IMAGES_RECEIVED,
                OrderStatus.PROCESSING,
                OrderStatus.WAITING_FOR_REVIEW,
                OrderStatus.PREVIEW_SENT,
                OrderStatus.WAITING_FOR_BUYER_CONFIRM,
            },
            OrderStatus.CANCELLED,
        ),
        OrderEvent.MARK_FAILED: (
            {
                OrderStatus.CREATED,
                OrderStatus.WAITING_FOR_IMAGES,
                OrderStatus.IMAGES_RECEIVED,
                OrderStatus.PROCESSING,
                OrderStatus.WAITING_FOR_REVIEW,
                OrderStatus.PREVIEW_SENT,
                OrderStatus.WAITING_FOR_BUYER_CONFIRM,
                OrderStatus.FINAL_SENT,
            },
            OrderStatus.FAILED,
        ),
    }

    def __init__(
        self,
        repository: OrderRepository | None = None,
        store: FileStore | None = None,
        processor: WatermarkProcessor | None = None,
        paths: ProjectPaths | None = None,
    ) -> None:
        self.repository = repository or order_repository
        self.store = store or file_store
        self.processor = processor or watermark_processor
        self.paths = paths or get_project_paths()

    # ---------------------------------------------------------------------
    # 查询
    # ---------------------------------------------------------------------

    def get_order(self, order_id: str) -> Order:
        order = self.repository.get_order(order_id)
        if order is None:
            raise OrderNotFoundError(f"Order not found: {order_id}")
        return order

    def list_orders(
        self,
        status: OrderStatus | None = None,
        limit: int = 50,
    ) -> list[Order]:
        return self.repository.list_orders(status=status, limit=limit)

    def list_state_logs(self, order_id: str) -> list[OrderStateLog]:
        return self.repository.list_state_logs(order_id)

    # ---------------------------------------------------------------------
    # 创建与收图
    # ---------------------------------------------------------------------

    def create_order(self, request: CreateOrderRequest | None = None) -> Order:
        request = request or CreateOrderRequest()

        order = Order(
            order_id=generate_order_id(),
            status=OrderStatus.CREATED,
            source_type=request.source_type,
            buyer_name=request.buyer_name,
            buyer_contact=request.buyer_contact,
            xianyu_order_id=request.xianyu_order_id,
            note=request.note,
            extra=request.extra,
        )

        self.paths.ensure_order_dirs(order.order_id)
        self._save(order)
        self._log_transition(
            order=order,
            from_status=None,
            to_status=OrderStatus.CREATED,
            event=OrderEvent.CREATE_ORDER,
            message="Order created",
        )
        return order

    def request_images(self, order_id: str) -> Order:
        order = self.get_order(order_id)
        return self._transition(
            order,
            OrderEvent.REQUEST_IMAGES,
            message="Requested buyer images",
        )

    def add_image(self, request: AddImageRequest) -> Order:
        """
        给订单添加一张原图。
        """
        order = self.get_order(request.order_id)

        original_path = self.store.copy_original_image(
            order_id=order.order_id,
            source_path=request.source_path,
            filename=request.filename,
        )

        image = OrderImage(
            image_id=generate_image_id(order.order_id),
            order_id=order.order_id,
            filename=original_path.name,
            source_type=request.source_type,
            status=ImageStatus.RECEIVED,
            original_path=original_path,
        )
        order.add_image(image)

        order = self._transition(
            order,
            OrderEvent.RECEIVE_IMAGES,
            message=f"Image received: {original_path.name}",
            save_before_transition=True,
        )
        return order

    def create_order_with_image(
        self,
        source_path: Path,
        source_type: SourceType = SourceType.FOLDER,
        buyer_name: str | None = None,
        buyer_contact: str | None = None,
        xianyu_order_id: str | None = None,
        note: str | None = None,
        extra: dict[str, object] | None = None,
    ) -> Order:
        """
        便捷方法：发现一张图片时，直接创建订单并添加图片。
        """
        order = self.create_order(
            CreateOrderRequest(
                buyer_name=buyer_name,
                buyer_contact=buyer_contact,
                xianyu_order_id=xianyu_order_id,
                source_type=source_type,
                note=note,
                extra=extra or {},
            )
        )

        return self.add_image(
            AddImageRequest(
                order_id=order.order_id,
                source_path=source_path,
                source_type=source_type,
                filename=source_path.name,
            )
        )

    # ---------------------------------------------------------------------
    # 处理与 edited / preview
    # ---------------------------------------------------------------------

    def start_processing(self, order_id: str) -> Order:
        order = self.get_order(order_id)
        if not order.images:
            raise ValueError(f"Order has no images: {order_id}")

        for image in order.images:
            if image.status in {ImageStatus.RECEIVED, ImageStatus.FAILED, ImageStatus.REJECTED}:
                image.mark_editing()

        return self._transition(
            order,
            OrderEvent.START_PROCESSING,
            message="Started image processing",
            save_before_transition=True,
        )

    def mark_image_edited(
        self,
        order_id: str,
        image_id: str,
        edited_source_path: Path,
    ) -> Order:
        """
        标记单张图片已经处理完成。

        适用场景：
        - 手动修图后，把图交给系统录入
        - 其他程序处理后，把结果图录入 edited
        """
        order = self.get_order(order_id)
        image = self._get_image(order, image_id)

        edited_path = self.store.copy_edited_image(
            order_id=order.order_id,
            source_path=edited_source_path,
            filename=image.filename,
        )
        image.mark_edited(edited_path)

        self._save(order)
        return order

    def process_order(
        self,
        order_id: str,
        processor_mode: str | None = None,
    ) -> Order:
        """
        统一处理入口。

        规则：
        - local：不自动生成 edited，等待你手动把修好的图放进 edited/
        - with_api：自动走 API 处理，再从 edited 生成 preview
        """
        settings = get_settings()
        mode = processor_mode or getattr(settings, "image_processor_mode", "local")

        if mode == "local":
            raise RuntimeError(
                "Local mode does not auto-generate edited images. "
                "Please manually place finished images into data/orders/{order_id}/edited/, "
                "then let edited_watcher generate previews."
            )

        if mode != "with_api":
            raise ValueError(f"Unsupported processor mode: {mode}")

        order = self.start_processing(order_id)

        processed_count = 0
        prompt = getattr(
            settings,
            "default_image_prompt",
            "在保持原始构图、人物特征和色彩关系的基础上，提升清晰度、修复模糊、优化细节质感，输出自然真实的高清效果图。",
        )

        for image in order.images:
            if image.original_path is None:
                image.mark_failed("Missing original image path")
                continue

            try:
                edited_path = self._process_single_image_with_api(
                    order=order,
                    image=image,
                    prompt=prompt,
                )
                image.mark_edited(edited_path)
                processed_count += 1
            except Exception as exc:
                image.mark_failed(str(exc))

        self._save(order)

        if processed_count == 0:
            return self.mark_failed(
                order.order_id,
                "All images failed during with_api processing",
            )

        return self.generate_previews(order.order_id)

    def _process_single_image_with_api(
        self,
        order: Order,
        image: OrderImage,
        prompt: str,
    ) -> Path:
        """
        with_api 接口预留点。

        你后续接入 OpenAI API 或其他图像处理后端时，
        就在这里完成“原图 -> edited 图”的处理，并返回生成后的 edited 路径。

        当前默认不实现，避免误以为 local 模式会自动生成 edited。
        """
        raise NotImplementedError(
            "with_api processor is reserved but not implemented yet. "
            "Implement your API backend here and return the final edited image path."
        )

    def generate_previews(self, order_id: str) -> Order:
        """
        仅从 edited 图片生成 preview。

        规则：
        - edited 有图：才允许生成 preview
        - original 不再作为兜底来源
        """
        order = self.get_order(order_id)

        if not order.images:
            raise ValueError(f"Order has no images: {order_id}")

        if order.status in {OrderStatus.IMAGES_RECEIVED, OrderStatus.FAILED}:
            for image in order.images:
                if image.status in {ImageStatus.RECEIVED, ImageStatus.REJECTED, ImageStatus.FAILED}:
                    image.mark_editing()

            order = self._transition(
                order,
                OrderEvent.START_PROCESSING,
                message="Started processing before preview generation",
                save_before_transition=True,
            )

        preview_count = 0

        for image in order.images:
            if image.edited_path is None:
                image.mark_failed("Edited image not found, cannot generate preview")
                continue

            preview_path = self.processor.generate_preview_with_watermark(
                order_id=order.order_id,
                source_path=image.edited_path,
                output_filename=image.filename,
            )
            image.mark_preview_generated(preview_path)
            preview_count += 1

        self._save(order)

        if preview_count == 0:
            return self.mark_failed(
                order.order_id,
                "No preview images were generated from edited images",
            )

        order = self._transition(
            order,
            OrderEvent.FINISH_PROCESSING,
            message="Generated watermarked previews from edited images",
            save_before_transition=True,
        )
        return order

    def process_order_without_ai(self, order_id: str) -> Order:
        """
        旧接口保留，但当前工作流已不再支持：
        “无 API 时自动复制 original 作为 edited”。

        现在 local 模式必须人工把处理完成图放进 edited/。
        """
        raise RuntimeError(
            "process_order_without_ai() is deprecated in the current workflow. "
            "In local mode, you must manually place finished images into edited/."
        )

    # ---------------------------------------------------------------------
    # 审核与交付状态
    # ---------------------------------------------------------------------

    def review_order(
        self,
        order_id: str,
        decision: ReviewDecision,
        message: str | None = None,
    ) -> Order:
        if decision == ReviewDecision.APPROVE:
            return self.approve_review(order_id, message=message)

        if decision == ReviewDecision.REJECT:
            return self.reject_review(order_id, message=message)

        if decision == ReviewDecision.REWORK:
            return self.reject_review(order_id, message=message or "Needs rework")

        raise ValueError(f"Unsupported review decision: {decision}")

    def approve_review(self, order_id: str, message: str | None = None) -> Order:
        order = self.get_order(order_id)

        for image in order.images:
            if image.status == ImageStatus.PREVIEW_GENERATED:
                image.mark_approved()

        return self._transition(
            order,
            OrderEvent.APPROVE_REVIEW,
            message=message or "Review approved",
            save_before_transition=True,
        )

    def reject_review(self, order_id: str, message: str | None = None) -> Order:
        order = self.get_order(order_id)

        for image in order.images:
            if image.status in {ImageStatus.PREVIEW_GENERATED, ImageStatus.APPROVED}:
                image.mark_rejected(message or "Rejected by reviewer")

        return self._transition(
            order,
            OrderEvent.REJECT_REVIEW,
            message=message or "Review rejected; back to processing",
            save_before_transition=True,
        )

    def mark_preview_sent(self, order_id: str) -> Order:
        order = self.get_order(order_id)
        return self._transition(
            order,
            OrderEvent.SEND_PREVIEW,
            message="Preview sent to buyer",
        )

    def mark_buyer_confirmed(self, order_id: str) -> Order:
        order = self.get_order(order_id)
        return self._transition(
            order,
            OrderEvent.BUYER_CONFIRMED,
            message="Buyer confirmed preview / receipt",
        )

    def prepare_final_images(self, order_id: str) -> Order:
        """
        准备最终交付图。
        默认从 edited 复制到 final。
        """
        order = self.get_order(order_id)

        for image in order.images:
            source_path = image.edited_path
            if source_path is None:
                image.mark_failed("Missing edited image for final delivery")
                continue

            final_path = self.store.copy_final_image(
                order_id=order.order_id,
                source_path=source_path,
                filename=image.filename,
            )
            image.mark_final_ready(final_path)

        self._save(order)
        return order

    def mark_final_sent(self, order_id: str) -> Order:
        order = self.prepare_final_images(order_id)
        return self._transition(
            order,
            OrderEvent.SEND_FINAL,
            message="Final images sent to buyer",
            save_before_transition=True,
        )

    def complete_order(self, order_id: str) -> Order:
        order = self.get_order(order_id)
        return self._transition(
            order,
            OrderEvent.COMPLETE_ORDER,
            message="Order completed",
        )

    def cancel_order(self, order_id: str, message: str | None = None) -> Order:
        order = self.get_order(order_id)
        return self._transition(
            order,
            OrderEvent.CANCEL_ORDER,
            message=message or "Order cancelled",
        )

    def mark_failed(self, order_id: str, error_message: str) -> Order:
        order = self.get_order(order_id)
        order.error_message = error_message
        return self._transition(
            order,
            OrderEvent.MARK_FAILED,
            message=error_message,
            save_before_transition=True,
        )

    # ---------------------------------------------------------------------
    # 内部工具
    # ---------------------------------------------------------------------

    def _transition(
        self,
        order: Order,
        event: OrderEvent,
        message: str | None = None,
        save_before_transition: bool = False,
    ) -> Order:
        allowed_from, to_status = self.TRANSITIONS[event]
        from_status = order.status

        if allowed_from is not None and from_status not in allowed_from:
            raise InvalidOrderTransitionError(
                f"Invalid transition: event={event.value}, "
                f"from={from_status.value}, to={to_status.value}"
            )

        if save_before_transition:
            self._save(order)

        order.set_status(to_status)
        self._save(order)
        self._log_transition(
            order=order,
            from_status=from_status,
            to_status=to_status,
            event=event,
            message=message,
        )
        return order

    def _save(self, order: Order) -> None:
        self.repository.save_order(order)
        self.store.save_order_metadata(order)

    def _log_transition(
        self,
        order: Order,
        from_status: OrderStatus | None,
        to_status: OrderStatus,
        event: OrderEvent,
        message: str | None = None,
    ) -> None:
        log = OrderStateLog(
            log_id=generate_log_id(),
            order_id=order.order_id,
            from_status=from_status,
            to_status=to_status,
            event=event.value,
            message=message,
        )
        self.repository.add_state_log(log)

    def _get_image(self, order: Order, image_id: str) -> OrderImage:
        for image in order.images:
            if image.image_id == image_id:
                return image
        raise ValueError(f"Image not found: {image_id}")


order_service = OrderService()