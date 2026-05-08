from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    全局配置入口。

    所有配置优先从 .env 读取；如果 .env 没有设置，则使用这里的默认值。
    后续如果你要切换成 OpenAI API、增加闲鱼监听源、换通知渠道，优先改这里。
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

    # OpenAI, optional for later
    enable_openai_api: bool = Field(default=False, alias="ENABLE_OPENAI_API")
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")

    # Paths
    data_dir: Path = Field(default=Path("data"), alias="DATA_DIR")
    incoming_dir: Path = Field(default=Path("data/incoming"), alias="INCOMING_DIR")
    orders_dir: Path = Field(default=Path("data/orders"), alias="ORDERS_DIR")
    database_path: Path = Field(
        default=Path("data/database/xianyu_photo_workflow.db"),
        alias="DATABASE_PATH",
    )

    # Image processing
    image_processor_mode: Literal["local", "with_api"] = Field(
        default="local",
        alias="IMAGE_PROCESSOR_MODE",
    )

    default_image_prompt: str = Field(
        default="在保持原始构图、人物特征和色彩关系的基础上，提升清晰度、修复模糊、优化细节质感，输出自然真实的高清效果图。",
        alias="DEFAULT_IMAGE_PROMPT",
    )
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
        """
        把 .env 里的字符串：
            .jpg,.jpeg,.png,.webp
        转成：
            (".jpg", ".jpeg", ".png", ".webp")
        """
        return tuple(
            item.strip().lower()
            for item in self.supported_image_extensions_raw.split(",")
            if item.strip()
        )

    @property
    def sqlite_url(self) -> str:
        """
        SQLAlchemy 使用的 SQLite 连接地址。
        """
        return f"sqlite:///{self.database_path.as_posix()}"

    def ensure_directories(self) -> None:
        """
        启动项目前，确保必要目录都存在。
        """
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.incoming_dir.mkdir(parents=True, exist_ok=True)
        self.orders_dir.mkdir(parents=True, exist_ok=True)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)

    def validate_runtime_config(self) -> None:
        """
        运行时校验。

        注意：不是所有模式都必须配置 Telegram。
        例如你只运行文件夹 worker 时，可以暂时不填 TELEGRAM_BOT_TOKEN。
        真正启动 bot 时再检查更合适。
        """
        if self.watermark_opacity < 0 or self.watermark_opacity > 255:
            raise ValueError("WATERMARK_OPACITY must be between 0 and 255")

        if self.preview_max_size <= 0:
            raise ValueError("PREVIEW_MAX_SIZE must be greater than 0")

        if self.watch_interval_seconds <= 0:
            raise ValueError("WATCH_INTERVAL_SECONDS must be greater than 0")

    def validate_telegram_config(self) -> None:
        """
        启动 Telegram Bot 前调用。
        """
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
    """
    缓存配置对象，避免项目里每个模块重复读取 .env。
    """
    return load_settings()
