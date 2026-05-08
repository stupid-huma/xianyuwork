from enum import StrEnum


class OrderStatus(StrEnum):
    """
    订单主状态。

    这个状态机用于描述一个闲鱼修图订单从创建到交付的完整生命周期。
    """

    CREATED = "created"
    WAITING_FOR_IMAGES = "waiting_for_images"
    IMAGES_RECEIVED = "images_received"
    PROCESSING = "processing"
    WAITING_FOR_REVIEW = "waiting_for_review"
    PREVIEW_SENT = "preview_sent"
    WAITING_FOR_BUYER_CONFIRM = "waiting_for_buyer_confirm"
    FINAL_SENT = "final_sent"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class ImageStatus(StrEnum):
    """
    单张图片状态。

    一个订单里可能包含多张图片，所以图片也需要自己的状态。
    """

    RECEIVED = "received"
    EDITING = "editing"
    EDITED = "edited"
    PREVIEW_GENERATED = "preview_generated"
    APPROVED = "approved"
    REJECTED = "rejected"
    FINAL_READY = "final_ready"
    FAILED = "failed"


class ReviewDecision(StrEnum):
    """
    审核决策。

    Telegram 里你可以通过按钮或命令做这些操作。
    """

    APPROVE = "approve"
    REJECT = "reject"
    REWORK = "rework"


class SourceType(StrEnum):
    """
    图片来源类型。

    当前先支持本地文件夹；后续可以扩展到闲鱼监听、QQ、Telegram、网页上传等。
    """

    FOLDER = "folder"
    XIAN_YU = "xian_yu"
    TELEGRAM = "telegram"
    QQ = "qq"
    MANUAL = "manual"


class DeliveryType(StrEnum):
    """
    交付类型。
    """

    PREVIEW = "preview"
    FINAL = "final"


class OrderEvent(StrEnum):
    """
    状态机事件。

    OrderService 不应该随意改状态，而应该通过事件驱动状态变化。
    这样以后接入闲鱼、Telegram、QQ 时，逻辑仍然清晰。
    """

    CREATE_ORDER = "create_order"
    REQUEST_IMAGES = "request_images"
    RECEIVE_IMAGES = "receive_images"
    START_PROCESSING = "start_processing"
    FINISH_PROCESSING = "finish_processing"
    SUBMIT_REVIEW = "submit_review"
    APPROVE_REVIEW = "approve_review"
    REJECT_REVIEW = "reject_review"
    SEND_PREVIEW = "send_preview"
    BUYER_CONFIRMED = "buyer_confirmed"
    SEND_FINAL = "send_final"
    COMPLETE_ORDER = "complete_order"
    CANCEL_ORDER = "cancel_order"
    MARK_FAILED = "mark_failed"
