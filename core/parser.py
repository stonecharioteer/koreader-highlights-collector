import re
from pathlib import Path
from typing import Dict, Any, Optional, List
from .schemas import ParsedFile, DocProps, ParserAnnotation


class LuaTableParser:
    """Simple parser for KoReader Lua metadata files (subset)."""

    @staticmethod
    def parse_file(filepath: Path) -> ParsedFile:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        match = re.search(r'return\s+({.*})', content, re.DOTALL)
        if not match:
            return ParsedFile()

        lua_table = match.group(1)
        return LuaTableParser._parse_table(lua_table)

    @staticmethod
    def _parse_table(lua_str: str) -> ParsedFile:
        annotations_str = LuaTableParser._extract_field_value(lua_str, 'annotations')
        annotations: List[ParserAnnotation] = []
        if annotations_str:
            annotations = LuaTableParser._parse_annotations(annotations_str)

        doc_props_str = LuaTableParser._extract_field_value(lua_str, 'doc_props')
        doc_props = DocProps()
        if doc_props_str:
            doc_props = LuaTableParser._parse_doc_props(doc_props_str)

        doc_path = None
        partial = None
        for field in ['doc_path', 'partial_md5_checksum']:
            match = re.search(rf'\["{field}"\]\s*=\s*"([^"]*)"', lua_str)
            if match:
                if field == 'doc_path':
                    doc_path = match.group(1)
                else:
                    partial = match.group(1)

        return ParsedFile(doc_props=doc_props, annotations=annotations, doc_path=doc_path, partial_md5_checksum=partial)

    @staticmethod
    def _extract_field_value(lua_str: str, field_name: str) -> Optional[str]:
        # Match ["field_name"] = { ... }
        pattern = r'\["{}"\]\s*=\s*\{{'.format(field_name)
        match = re.search(pattern, lua_str)
        if not match:
            return None

        start_pos = match.end() - 1
        brace_depth = 0
        end_pos = start_pos

        for i in range(start_pos, len(lua_str)):
            char = lua_str[i]
            if char == '{':
                brace_depth += 1
            elif char == '}':
                brace_depth -= 1
                if brace_depth == 0:
                    end_pos = i
                    break

        if brace_depth == 0:
            return lua_str[start_pos + 1:end_pos]

        return None

    @staticmethod
    def _unescape_lua_string(s: str) -> str:
        """Unescape Lua string escape sequences.

        Order matters: handle \\\\ first to avoid double-unescaping.
        """
        # Replace escape sequences in order from most specific to least
        s = s.replace(r'\\', '\x00')  # Temporarily replace \\ with placeholder
        s = s.replace(r'\"', '"')
        s = s.replace(r"\'", "'")
        s = s.replace(r'\n', '\n')
        s = s.replace(r'\r', '\r')
        s = s.replace(r'\t', '\t')
        s = s.replace('\x00', '\\')  # Restore actual backslashes
        return s

    @staticmethod
    def _parse_annotations(annotations_str: str) -> List[ParserAnnotation]:
        annotations: List[ParserAnnotation] = []
        blocks = []
        current_block = []
        brace_depth = 0
        in_annotation = False

        for line in annotations_str.split('\n'):
            if re.match(r'\s*\[\d+\]\s*=\s*\{', line):
                if current_block:
                    blocks.append('\n'.join(current_block))
                current_block = [line]
                brace_depth = 1
                in_annotation = True
            elif in_annotation:
                current_block.append(line)
                brace_depth += line.count('{') - line.count('}')
                if brace_depth == 0:
                    blocks.append('\n'.join(current_block))
                    current_block = []
                    in_annotation = False

        for block in blocks:
            values: Dict[str, Any] = {}
            for field in ['chapter', 'color', 'datetime', 'page', 'text', 'drawer', 'pos0', 'pos1']:
                match = re.search(rf'\["{field}"\]\s*=\s*"((?:[^"\\]|\\.)*)"', block)
                if match:
                    values[field] = LuaTableParser._unescape_lua_string(match.group(1))
            match = re.search(r'\["pageno"\]\s*=\s*(\d+)', block)
            if match:
                values['pageno'] = int(match.group(1))
            if values:
                annotations.append(ParserAnnotation(**values))
        return annotations

    @staticmethod
    def _parse_doc_props(doc_props_str: str) -> DocProps:
        values: Dict[str, Any] = {}
        for field in ['authors', 'title', 'language', 'description', 'identifiers', 'series']:
            match = re.search(rf'\["{field}"\]\s*=\s*"((?:[^"\\]|\\.)*)"', doc_props_str)
            if match:
                values[field] = LuaTableParser._unescape_lua_string(match.group(1))
        return DocProps(**values)
