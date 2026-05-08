from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

from app.core.models import Order
from config.paths import ProjectPaths, get_project_paths
from config.settings import get_settings


class FileStore:
    """
    文件存储层。

    职责：
    - 管理订单目录
    - 保存 / 读取 metadata.json
    - 把 incoming 图片复制到订单目录
    - 把 edited / preview / final 图片复制到对应目录

    注意：
    这个类不负责状态机判断，只负责文件层面的读写。
    """

    def __init__(self, paths: ProjectPaths | None = None) -> None:
        self.paths = paths or get_project_paths()
        self.settings = get_settings()

    def ensure_order_dirs(self, order_id: str) -> None:
        self.paths.ensure_order_dirs(order_id)

    def save_order_metadata(self, order: Order) -> Path:
        """
        保存订单 metadata.json。

        SQLite 是主存储，metadata.json 主要方便人工排查和备份。
        """
        self.ensure_order_dirs(order.order_id)
        metadata_path = self.paths.metadata_path(order.order_id)

        with metadata_path.open("w", encoding="utf-8") as f:
            json.dump(order.to_metadata_dict(), f, ensure_ascii=False, indent=2)

        return metadata_path

    def load_order_metadata(self, order_id: str) -> Order | None:
        """
        从 metadata.json 读取订单。
        """
        metadata_path = self.paths.metadata_path(order_id)
        if not metadata_path.exists():
            return None

        with metadata_path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        return Order.from_metadata_dict(data)

    def list_incoming_images(self) -> list[Path]:
        """
        列出 incoming 目录下的图片。
        """
        incoming_dir = self.paths.incoming_dir
        incoming_dir.mkdir(parents=True, exist_ok=True)

        files = [
            path
            for path in incoming_dir.iterdir()
            if path.is_file() and self.paths.is_supported_image(path)
        ]
        return sorted(files, key=lambda item: item.stat().st_mtime)

    def copy_original_image(
        self,
        order_id: str,
        source_path: Path,
        filename: str | None = None,
    ) -> Path:
        """
        把买家原图复制到订单 original 目录。
        """
        self._validate_image_file(source_path)
        self.ensure_order_dirs(order_id)

        safe_name = self._build_safe_filename(source_path, filename)
        target_path = self.paths.build_original_image_path(order_id, safe_name)
        target_path = self._avoid_overwrite(target_path)

        shutil.copy2(source_path, target_path)
        return target_path

    def copy_edited_image(
        self,
        order_id: str,
        source_path: Path,
        filename: str | None = None,
    ) -> Path:
        """
        把处理后的高清图复制到订单 edited 目录。
        """
        self._validate_image_file(source_path)
        self.ensure_order_dirs(order_id)

        safe_name = self._build_safe_filename(source_path, filename)
        target_path = self.paths.build_edited_image_path(order_id, safe_name)
        target_path = self._avoid_overwrite(target_path)

        shutil.copy2(source_path, target_path)
        return target_path

    def copy_preview_image(
        self,
        order_id: str,
        source_path: Path,
        filename: str | None = None,
    ) -> Path:
        """
        把水印预览图复制到订单 preview 目录。
        """
        self._validate_image_file(source_path)
        self.ensure_order_dirs(order_id)

        safe_name = self._build_safe_filename(source_path, filename)
        target_path = self.paths.build_preview_image_path(order_id, safe_name)
        target_path = self._avoid_overwrite(target_path)

        shutil.copy2(source_path, target_path)
        return target_path

    def copy_final_image(
        self,
        order_id: str,
        source_path: Path,
        filename: str | None = None,
    ) -> Path:
        """
        把最终交付图复制到订单 final 目录。
        """
        self._validate_image_file(source_path)
        self.ensure_order_dirs(order_id)

        safe_name = self._build_safe_filename(source_path, filename)
        target_path = self.paths.build_final_image_path(order_id, safe_name)
        target_path = self._avoid_overwrite(target_path)

        shutil.copy2(source_path, target_path)
        return target_path

    def wait_until_file_stable(
        self,
        path: Path,
        stable_seconds: float = 1.0,
        timeout_seconds: float = 20.0,
    ) -> bool:
        """
        等待文件写入完成。

        文件夹监听时经常会遇到：文件刚出现，但还没复制完成。
        这个方法通过观察文件大小是否稳定，降低读到半截文件的概率。
        """
        start_time = time.time()
        last_size = -1
        stable_start: float | None = None

        while time.time() - start_time <= timeout_seconds:
            if not path.exists() or not path.is_file():
                time.sleep(0.2)
                continue

            current_size = path.stat().st_size

            if current_size == last_size and current_size > 0:
                if stable_start is None:
                    stable_start = time.time()
                elif time.time() - stable_start >= stable_seconds:
                    return True
            else:
                stable_start = None
                last_size = current_size

            time.sleep(0.2)

        return False

    def _validate_image_file(self, path: Path) -> None:
        if not path.exists():
            raise FileNotFoundError(f"Image file does not exist: {path}")

        if not path.is_file():
            raise ValueError(f"Path is not a file: {path}")

        if not self.paths.is_supported_image(path):
            raise ValueError(
                f"Unsupported image extension: {path.suffix}. "
                f"Supported: {self.settings.supported_image_extensions}"
            )

    def _build_safe_filename(self, source_path: Path, filename: str | None = None) -> str:
        """
        生成安全文件名。

        这里只做基础清洗：
        - 去掉目录部分
        - 空格替换成下划线
        - 保留原始后缀
        """
        raw_name = filename or source_path.name
        raw_path = Path(raw_name)

        stem = raw_path.stem.strip().replace(" ", "_") or source_path.stem
        suffix = raw_path.suffix or source_path.suffix

        allowed_chars = []
        for char in stem:
            if char.isalnum() or char in {"_", "-", "."}:
                allowed_chars.append(char)
            else:
                allowed_chars.append("_")

        safe_stem = "".join(allowed_chars).strip("._") or "image"
        return f"{safe_stem}{suffix.lower()}"

    def _avoid_overwrite(self, target_path: Path) -> Path:
        """
        避免覆盖已有文件。

        如果 image.jpg 已存在，则生成：
            image_001.jpg
            image_002.jpg
        """
        if not target_path.exists():
            return target_path

        stem = target_path.stem
        suffix = target_path.suffix
        parent = target_path.parent

        index = 1
        while True:
            candidate = parent / f"{stem}_{index:03d}{suffix}"
            if not candidate.exists():
                return candidate
            index += 1


file_store = FileStore()
