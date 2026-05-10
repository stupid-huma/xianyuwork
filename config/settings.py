from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# -------------------------------------------------------------------------
#
#
# -------------------------------------------------------------------------
class Settings(BaseSettings):
    """
    Global configuration entrypoint.

    Runtime secrets still come from .env. Workflow switches such as
    image_processor_mode, api_provider, and image_prompt_mode are intentionally
    kept in this file so there is only one place to change processing behavior.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    app_env: Literal["dev", "prod"] = Field(default="dev", alias="APP_ENV")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO",
        alias="LOG_LEVEL",
    )

    # Telegram
    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    telegram_admin_user_id: int | None = Field(
        default=None,
        alias="TELEGRAM_ADMIN_USER_ID",
    )

    # API secrets. Do not put provider switches in .env.
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")                    #OpenAI
    qwen_api_key: str = Field(                                                          #千问
        default="",
        validation_alias=AliasChoices("QWEN_API_KEY", "DASHSCOPE_API_KEY"),
    )
    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")                      #Gemini
    leonardo_api_key: str = Field(default="", alias="LEONARDO_API_KEY")                  #Leonardo
    doubao_api_key: str = Field(                                                         #豆包
        default="",
        validation_alias=AliasChoices("DOUBAO_API_KEY", "ARK_API_KEY"),
    )

    # Paths
    data_dir: Path = Field(default=Path("data"), alias="DATA_DIR")
    incoming_dir: Path = Field(default=Path("data/incoming"), alias="INCOMING_DIR")
    orders_dir: Path = Field(default=Path("data/orders"), alias="ORDERS_DIR")
    database_path: Path = Field(
        default=Path("data/database/xianyu_photo_workflow.db"),
        alias="DATABASE_PATH",
    )

# -------------------------------------------------------------------------
#|                                                                         |
#|                                切换API                                   |
#|                                                                         |
#|                                                                         |
# -------------------------------------------------------------------------

    # Image workflow switches. Change these in settings.py, not .env.
    image_processor_mode: Literal["local", "api"] = "api"                          #！！！改这里
    # 可选值：
    # - "qwen"
    # - "openai"
    # - "gemini_flash"
    # - "gemini_pro"
    # - "leonardo"
    # - "doubao"
    #
    # 例如要调用 Gemini Flash，就把下一行最后的默认值改成 "gemini_flash"。
    api_provider: Literal[
        "qwen",
        "openai",
        "gemini",
        "gemini_flash",
        "gemini_pro",
        "leonardo",
        "doubao",
    ] = "qwen"                                                                      #！！！改这里

# -------------------------------------------------------------------------
# |                                                                         |
# |                              切换提示词                                   |
# |                                                                         |
# |                                                                         |
# -------------------------------------------------------------------------
    # 可选值：
    # - "repair"：修复/增强买家原图，尽量保持原始构图和人物特征。
    # - "reference_generate"：参考输入图生成新图，允许姿势/构图发生明显变化。
    # - "custom"：完全使用 custom_image_prompt。
    image_prompt_mode: Literal["repair", "reference_generate", "custom"] = "reference_generate"  #！！！改这里

    repair_image_prompt: str = (
        "在保持原始构图、人物特征和色彩关系的基础上，提升清晰度、修复模糊、"
        "优化细节质感，输出自然真实的高清效果图。"
    )
    reference_generation_prompt: str = (
        "参考输入图的角色、画风、服饰、色彩和核心视觉元素，生成一张油画新图。"
        "允许重新构图和改变动作，不要只做清晰度修复；输出自然完整、细节丰富的成图。"
    )
    custom_image_prompt: str = ""

# -------------------------------------------------------------------------
#                       换模型版本
# -------------------------------------------------------------------------
    # OpenAI image API settings.
    openai_image_model: str = "gpt-image-1.5"

    # Qwen / DashScope image API settings.
    qwen_endpoint: str = (
        "https://dashscope.aliyuncs.com/api/v1/services/aigc/"
        "multimodal-generation/generation"
    )
    qwen_image_model: str = "qwen-image-2.0-pro"
    qwen_image_count: int = 1
    qwen_negative_prompt: str = " "
    qwen_prompt_extend: bool = True
    qwen_watermark: bool = False
    qwen_image_size: str = ""

    # Google Gemini native image generation/editing settings.
    gemini_endpoint_base_url: str = "https://generativelanguage.googleapis.com/v1beta/models"
    gemini_image_model: str = "gemini-3.1-flash-image-preview"
    gemini_flash_image_model: str = "gemini-3.1-flash-image-preview"
    gemini_pro_image_model: str = "gemini-3-pro-image-preview"
    gemini_response_modalities: tuple[str, str] = ("TEXT", "IMAGE")

    # Leonardo.Ai image-to-image settings.
    leonardo_api_base_url: str = "https://cloud.leonardo.ai/api/rest/v1"
    leonardo_model_id: str = "b24e16ff-06e3-43eb-8d33-4416c2d75876"
    leonardo_width: int = 1024
    leonardo_height: int = 1024
    leonardo_num_images: int = 1
    leonardo_init_strength: float = 0.5
    leonardo_alchemy: bool = True
    leonardo_preset_style: str = "DYNAMIC"
    leonardo_poll_interval_seconds: float = 3.0
    leonardo_max_poll_attempts: int = 60

    # Doubao / Volcengine Ark Seedream image settings.
    doubao_api_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    doubao_image_model: str = "doubao-seedream-4-5-251128"
    doubao_response_format: Literal["url", "b64_json"] = "b64_json"
    doubao_size: str = "2K"
    doubao_watermark: bool = False
    doubao_seed: int | None = None
    doubao_guidance_scale: float | None = None
# -------------------------------------------------------------------------

    api_request_timeout_seconds: float = 180.0

    # Local preview processing
    watermark_text: str = Field(default="PREVIEW", alias="WATERMARK_TEXT")
    watermark_opacity: int = Field(default=90, alias="WATERMARK_OPACITY")
    preview_max_size: int = Field(default=1600, alias="PREVIEW_MAX_SIZE")
    supported_image_extensions_raw: str = Field(
        default=".jpg,.jpeg,.png,.webp",
        alias="SUPPORTED_IMAGE_EXTENSIONS",
    )

    # Watchers
    watch_interval_seconds: float = Field(default=2.0, alias="WATCH_INTERVAL_SECONDS")

    @property
    def supported_image_extensions(self) -> tuple[str, ...]:
        return tuple(
            item.strip().lower()
            for item in self.supported_image_extensions_raw.split(",")
            if item.strip()
        )

    @property
    def selected_image_prompt(self) -> str:
        if self.image_prompt_mode == "repair":
            return self.repair_image_prompt

        if self.image_prompt_mode == "reference_generate":
            return self.reference_generation_prompt

        if self.image_prompt_mode == "custom":
            return self.custom_image_prompt

        raise ValueError(f"Unsupported image_prompt_mode: {self.image_prompt_mode}")

    @property
    def default_image_prompt(self) -> str:
        """
        Backward-compatible name for callers that have not switched to
        selected_image_prompt yet.
        """
        return self.selected_image_prompt

    @property
    def sqlite_url(self) -> str:
        return f"sqlite:///{self.database_path.as_posix()}"

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.incoming_dir.mkdir(parents=True, exist_ok=True)
        self.orders_dir.mkdir(parents=True, exist_ok=True)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)

    def validate_runtime_config(self) -> None:
        if self.image_processor_mode not in {"local", "api"}:
            raise ValueError("image_processor_mode must be either 'local' or 'api'")

        if self.image_prompt_mode not in {"repair", "reference_generate", "custom"}:
            raise ValueError("image_prompt_mode must be one of: repair, reference_generate, custom")

        if self.image_prompt_mode == "custom" and not self.custom_image_prompt.strip():
            raise ValueError("custom_image_prompt is required when image_prompt_mode='custom'")

        if not self.selected_image_prompt.strip():
            raise ValueError("selected image prompt must not be empty")

        supported_api_providers = {
            "qwen",
            "openai",
            "gemini",
            "gemini_flash",
            "gemini_pro",
            "leonardo",
            "doubao",
        }
        if self.api_provider not in supported_api_providers:
            raise ValueError(
                "api_provider must be one of: "
                + ", ".join(sorted(supported_api_providers))
            )

        if self.image_processor_mode == "api":
            if self.api_provider == "openai" and not self.openai_api_key:
                raise ValueError("OPENAI_API_KEY is required when api_provider='openai'")

            if self.api_provider == "qwen" and not self.qwen_api_key:
                raise ValueError("QWEN_API_KEY or DASHSCOPE_API_KEY is required when api_provider='qwen'")

            if self.api_provider in {"gemini", "gemini_flash", "gemini_pro"} and not self.gemini_api_key:
                raise ValueError("GEMINI_API_KEY is required when api_provider uses Gemini")

            if self.api_provider == "leonardo" and not self.leonardo_api_key:
                raise ValueError("LEONARDO_API_KEY is required when api_provider='leonardo'")

            if self.api_provider == "doubao" and not self.doubao_api_key:
                raise ValueError("DOUBAO_API_KEY or ARK_API_KEY is required when api_provider='doubao'")

        if self.leonardo_width <= 0 or self.leonardo_height <= 0:
            raise ValueError("Leonardo width and height must be greater than 0")

        if self.leonardo_num_images < 1 or self.leonardo_num_images > 8:
            raise ValueError("leonardo_num_images must be between 1 and 8")

        if self.leonardo_init_strength < 0.1 or self.leonardo_init_strength > 0.9:
            raise ValueError("leonardo_init_strength must be between 0.1 and 0.9")

        if self.leonardo_poll_interval_seconds <= 0:
            raise ValueError("leonardo_poll_interval_seconds must be greater than 0")

        if self.leonardo_max_poll_attempts <= 0:
            raise ValueError("leonardo_max_poll_attempts must be greater than 0")

        if self.watermark_opacity < 0 or self.watermark_opacity > 255:
            raise ValueError("WATERMARK_OPACITY must be between 0 and 255")

        if self.preview_max_size <= 0:
            raise ValueError("PREVIEW_MAX_SIZE must be greater than 0")

        if self.watch_interval_seconds <= 0:
            raise ValueError("WATCH_INTERVAL_SECONDS must be greater than 0")

    def validate_telegram_config(self) -> None:
        if not self.telegram_bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN is required to run Telegram bot")

        if self.telegram_admin_user_id is None:
            raise ValueError("TELEGRAM_ADMIN_USER_ID is required to run Telegram bot")


def load_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    settings.validate_runtime_config()
    return settings


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()
