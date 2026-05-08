from __future__ import annotations

import shutil
from pathlib import Path

from app.core.enums import SourceType
from app.sources.base import ImageSource, SourceImage
from config.paths import ProjectPaths, get_project_paths


class FolderImageSource(ImageSource):
    """
    本地文件夹图片来源。

    默认扫描：
        data/incoming/

    发现图片后返回 SourceImage。
    当 worker 成功接收图片后，会调用 mark_consumed()，把原始 incoming 文件移动到：
        data/incoming/_consumed/

    如果处理失败，会调用 mark_failed()，把文件移动到：
        data/incoming/_failed/
    """

    source_type = SourceType.FOLDER

    def __init__(
        self,
        incoming_dir: Path | None = None,
        paths: ProjectPaths | None = None,
    ) -> None:
        self.paths = paths or get_project_paths()
        self.incoming_dir = incoming_dir or self.paths.incoming_dir
        self.consumed_dir = self.incoming_dir / "_consumed"
        self.failed_dir = self.incoming_dir / "_failed"

        self.incoming_dir.mkdir(parents=True, exist_ok=True)
        self.consumed_dir.mkdir(parents=True, exist_ok=True)
        self.failed_dir.mkdir(parents=True, exist_ok=True)

    def discover_images(self) -> list[SourceImage]:
        """
        扫描 incoming 目录下的图片。

        注意：
        - 不递归扫描子目录
        - 跳过 _consumed 和 _failed
        - 按修改时间排序，先处理旧文件
        """
        candidates: list[Path] = []

        for path in self.incoming_dir.iterdir():
            if not path.is_file():
                continue

            if not self.paths.is_supported_image(path):
                continue

            candidates.append(path)

        candidates.sort(key=lambda item: item.stat().st_mtime)

        return [
            SourceImage(
                source_path=path,
                source_type=self.source_type,
                filename=path.name,
                note="Discovered from local incoming folder",
                extra={
                    "source": "folder",
                    "incoming_path": path.as_posix(),
                    "modified_time": path.stat().st_mtime,
                },
            )
            for path in candidates
        ]

    def mark_consumed(self, image: SourceImage) -> None:
        """
        成功接收后，把 incoming 文件移动到 _consumed。
        """
        self._move_to_directory(image.source_path, self.consumed_dir)

    def mark_failed(self, image: SourceImage, error: Exception) -> None:
        """
        处理失败后，把 incoming 文件移动到 _failed。
        """
        target_path = self._move_to_directory(image.source_path, self.failed_dir)

        error_path = target_path.with_suffix(target_path.suffix + ".error.txt")
        error_path.write_text(str(error), encoding="utf-8")

    def _move_to_directory(self, source_path: Path, target_dir: Path) -> Path:
        """
        移动文件到目标目录，并避免重名覆盖。
        """
        if not source_path.exists():
            return target_dir / source_path.name

        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = self._avoid_overwrite(target_dir / source_path.name)

        shutil.move(source_path.as_posix(), target_path.as_posix())
        return target_path

    def _avoid_overwrite(self, target_path: Path) -> Path:
        if not target_path.exists():
            return target_path

        parent = target_path.parent
        stem = target_path.stem
        suffix = target_path.suffix

        index = 1
        while True:
            candidate = parent / f"{stem}_{index:03d}{suffix}"
            if not candidate.exists():
                return candidate
            index += 1


folder_image_source = FolderImageSource()
