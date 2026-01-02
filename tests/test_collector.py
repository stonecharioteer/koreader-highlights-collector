from pathlib import Path

from core.collector import iter_metadata_files


def test_iter_metadata_files_finds_samples():
    base = Path("sample-highlights")
    files = list(iter_metadata_files(base))
    assert files, "Expected iter_metadata_files to find sample metadata files"
    assert all(f.name.startswith("metadata.") and f.suffix == ".lua" for f in files)
