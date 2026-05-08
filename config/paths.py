from pathlib import Path

from config.settings import get_settings


class ProjectPaths:
    """
    项目路径管理器。

    settings.py 负责读取 .env；
    paths.py 负责把业务路径组织成更好用的方法。

    后续订单文件、原图、预览图、高清图、水印图，都会通过这里统一生成路径。
    """

    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def data_dir(self) -> Path:
        return self.settings.data_dir

    @property
    def incoming_dir(self) -> Path:
        return self.settings.incoming_dir

    @property
    def orders_dir(self) -> Path:
        return self.settings.orders_dir

    @property
    def database_path(self) -> Path:
        return self.settings.database_path

    def order_dir(self, order_id: str) -> Path:
        """
        单个订单的根目录。

        示例：
            data/orders/ORD_20260507_000001/
        """
        return self.orders_dir / order_id

    def original_dir(self, order_id: str) -> Path:
        """
        买家原始图片目录。
        """
        return self.order_dir(order_id) / "original"

    def edited_dir(self, order_id: str) -> Path:
        """
        GPT 或人工处理后的高清图目录。
        """
        return self.order_dir(order_id) / "edited"

    def preview_dir(self, order_id: str) -> Path:
        """
        加水印预览图目录。
        """
        return self.order_dir(order_id) / "preview"

    def final_dir(self, order_id: str) -> Path:
        """
        最终交付目录，通常存放无水印高清版本。
        """
        return self.order_dir(order_id) / "final"

    def metadata_path(self, order_id: str) -> Path:
        """
        单个订单的元数据 JSON 文件。

        虽然主状态存在 SQLite，保留 metadata.json 方便人工查看和备份。
        """
        return self.order_dir(order_id) / "metadata.json"

    def ensure_order_dirs(self, order_id: str) -> None:
        """
        创建一个订单所需的所有目录。
        """
        self.order_dir(order_id).mkdir(parents=True, exist_ok=True)
        self.original_dir(order_id).mkdir(parents=True, exist_ok=True)
        self.edited_dir(order_id).mkdir(parents=True, exist_ok=True)
        self.preview_dir(order_id).mkdir(parents=True, exist_ok=True)
        self.final_dir(order_id).mkdir(parents=True, exist_ok=True)

    def build_original_image_path(self, order_id: str, filename: str) -> Path:
        return self.original_dir(order_id) / filename

    def build_edited_image_path(self, order_id: str, filename: str) -> Path:
        return self.edited_dir(order_id) / filename

    def build_preview_image_path(self, order_id: str, filename: str) -> Path:
        stem = Path(filename).stem
        suffix = Path(filename).suffix or ".jpg"
        return self.preview_dir(order_id) / f"{stem}_preview{suffix}"

    def build_final_image_path(self, order_id: str, filename: str) -> Path:
        return self.final_dir(order_id) / filename

    def is_supported_image(self, path: Path) -> bool:
        """
        判断文件是否是支持的图片格式。
        """
        return path.suffix.lower() in self.settings.supported_image_extensions


def get_project_paths() -> ProjectPaths:
    """
    获取路径管理器。

    这里暂时不做 lru_cache，方便测试时切换 .env 或临时目录。
    """
    return ProjectPaths()
