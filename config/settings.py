from functools import lru_cache
from pathlib import Path
from typing import ClassVar, Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Global configuration entrypoint.

    Runtime secrets still come from .env. Workflow switches such as
    image_processor_mode, api_provider, and default_image_prompt are intentionally
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
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    qwen_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("QWEN_API_KEY", "DASHSCOPE_API_KEY"),
    )

    # Paths
    data_dir: Path = Field(default=Path("data"), alias="DATA_DIR")
    incoming_dir: Path = Field(default=Path("data/incoming"), alias="INCOMING_DIR")
    orders_dir: Path = Field(default=Path("data/orders"), alias="ORDERS_DIR")
    database_path: Path = Field(
        default=Path("data/database/xianyu_photo_workflow.db"),
        alias="DATABASE_PATH",
    )

    # Image workflow switches. Change these in settings.py, not .env.
    image_processor_mode: Literal["local", "api"] = "local"
    api_provider: Literal["qwen", "openai"] = "qwen"
    default_image_prompt: str = (
        "在保持原始构图、人物特征和色彩关系的基础上，提升清晰度、修复模糊、"
        "优化细节质感，输出自然真实的高清效果图。"
    )

    # OpenAI image API settings.
    openai_image_model: str = "gpt-image-1"

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

        if self.api_provider not in {"qwen", "openai"}:
            raise ValueError("api_provider must be either 'qwen' or 'openai'")

        if self.image_processor_mode == "api":
            if self.api_provider == "openai" and not self.openai_api_key:
                raise ValueError("OPENAI_API_KEY is required when api_provider='openai'")

            if self.api_provider == "qwen" and not self.qwen_api_key:
                raise ValueError("QWEN_API_KEY or DASHSCOPE_API_KEY is required when api_provider='qwen'")

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
