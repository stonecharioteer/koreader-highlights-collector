from pathlib import Path
import re

import pytest

from core.parser import LuaTableParser
from core.schemas import ParsedFile, HighlightKind


def test_parse_file_structure_from_sample():
    sample_root = Path("sample-highlights")
    files = list(sample_root.rglob("metadata.*.lua"))
    assert files, "Expected at least one metadata.*.lua under sample-highlights"

    data = LuaTableParser.parse_file(files[0])
    assert isinstance(data, ParsedFile)
    assert isinstance(data.annotations, list)
    assert data.doc_props is not None

    # Spot-check doc_props may include a title/authors when present
    # Don't assert exact values to keep the test robust
    if data.doc_props:
        # Some samples may lack authors; require at least title when present
        assert hasattr(data.doc_props, "title")


def test_annotations_fields_present_when_available():
    sample_root = Path("sample-highlights")
    files = list(sample_root.rglob("metadata.*.lua"))
    data = LuaTableParser.parse_file(files[0])
    annotations = data.annotations or []
    # If annotations exist, they should be dict-like entries parsed from Lua
    if annotations:
        a0 = annotations[0]
        # Not all fields are mandatory, but if present must be correct type
        for key in ["chapter", "color", "datetime", "page", "text", "drawer"]:
            if getattr(a0, key, None) is not None:
                assert isinstance(getattr(a0, key), str)
        assert isinstance(a0.kind, HighlightKind)
