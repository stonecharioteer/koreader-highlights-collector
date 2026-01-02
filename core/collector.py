from pathlib import Path
from typing import Iterator


def iter_metadata_files(base_path: Path) -> Iterator[Path]:
    """Yield all KoReader metadata.*.lua files under device folders."""
    if not base_path.exists():
        return
    for device_folder in base_path.iterdir():
        if not device_folder.is_dir():
            continue
        for metadata_file in device_folder.rglob("metadata.*.lua"):
            yield metadata_file
