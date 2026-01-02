from typing import List, Optional
from enum import Enum
from pydantic import BaseModel, model_validator


class HighlightKind(str, Enum):
    highlight = "highlight"
    highlight_empty = "highlight_empty"
    highlight_no_position = "highlight_no_position"
    bookmark = "bookmark"
    unknown = "unknown"


class ParserAnnotation(BaseModel):
    chapter: Optional[str] = None
    color: Optional[str] = None
    datetime: Optional[str] = None
    page: Optional[str] = None
    text: Optional[str] = None
    drawer: Optional[str] = None
    pos0: Optional[str] = None
    pos1: Optional[str] = None
    pageno: Optional[int] = None
    kind: HighlightKind = HighlightKind.unknown

    @model_validator(mode="after")
    def set_kind(self):
        has_color = bool(self.color)
        has_text = bool(self.text)
        has_positions = bool(self.pos0 and self.pos1)

        if has_color and has_text and has_positions:
            self.kind = HighlightKind.highlight
        elif has_color and has_positions and not has_text:
            self.kind = HighlightKind.highlight_empty
        elif has_color and not has_positions:
            self.kind = HighlightKind.highlight_no_position
        elif not has_color and has_text:
            self.kind = HighlightKind.bookmark
        else:
            self.kind = HighlightKind.unknown
        return self


class DocProps(BaseModel):
    authors: Optional[str] = None
    title: Optional[str] = None
    language: Optional[str] = None
    description: Optional[str] = None
    identifiers: Optional[str] = None
    series: Optional[str] = None


class ParsedFile(BaseModel):
    doc_props: DocProps = DocProps()
    annotations: List[ParserAnnotation] = []
    partial_md5_checksum: Optional[str] = None
    doc_path: Optional[str] = None
