#!/usr/bin/env python3
"""
KoReader Highlights Collector

Scans syncthing directories for KoReader metadata files and collects all highlights
into a single JSON file, grouped by book.
"""

import os
import json
import re
from pathlib import Path
from typing import Dict, List, Any
from datetime import datetime
import argparse


class LuaTableParser:
    """Simple parser for KoReader Lua metadata files."""

    @staticmethod
    def parse_file(filepath: Path) -> Dict[str, Any]:
        """Parse a Lua metadata file and return a Python dict."""
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        # Extract the return statement content
        match = re.search(r'return\s+({.*})', content, re.DOTALL)
        if not match:
            return {}

        lua_table = match.group(1)
        return LuaTableParser._parse_table(lua_table)

    @staticmethod
    def _parse_table(lua_str: str) -> Dict[str, Any]:
        """Parse a Lua table string into a Python dict."""
        # This is a simplified parser for the specific KoReader metadata format
        # It handles the basic structure we need for annotations

        result = {}

        # Find annotations array using proper brace matching
        annotations_str = LuaTableParser._extract_field_value(lua_str, 'annotations')
        if annotations_str:
            result['annotations'] = LuaTableParser._parse_annotations(annotations_str)

        # Extract doc_props
        doc_props_str = LuaTableParser._extract_field_value(lua_str, 'doc_props')
        if doc_props_str:
            result['doc_props'] = LuaTableParser._parse_doc_props(doc_props_str)

        # Extract simple string fields
        for field in ['doc_path', 'partial_md5_checksum']:
            match = re.search(rf'\["{field}"\]\s*=\s*"([^"]*)"', lua_str)
            if match:
                result[field] = match.group(1)

        return result

    @staticmethod
    def _extract_field_value(lua_str: str, field_name: str) -> str:
        """Extract a field's value from Lua table, handling nested braces."""
        # Find the start of the field
        pattern = rf'\["{field_name}"\]\s*=\s*\{{'
        match = re.search(pattern, lua_str)
        if not match:
            return None

        start_pos = match.end() - 1  # Position of opening brace
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
            # Extract content between braces (not including the braces themselves)
            return lua_str[start_pos + 1:end_pos]

        return None

    @staticmethod
    def _parse_annotations(annotations_str: str) -> List[Dict[str, Any]]:
        """Parse the annotations array from Lua."""
        annotations = []

        # Split into individual annotation blocks by looking for [N] = {
        # We need to handle nested braces properly
        blocks = []
        current_block = []
        brace_depth = 0
        in_annotation = False

        for line in annotations_str.split('\n'):
            # Check if this is the start of an annotation block
            if re.match(r'\s*\[\d+\]\s*=\s*\{', line):
                if current_block:
                    blocks.append('\n'.join(current_block))
                current_block = [line]
                brace_depth = 1
                in_annotation = True
            elif in_annotation:
                current_block.append(line)
                # Count braces
                brace_depth += line.count('{') - line.count('}')
                if brace_depth == 0:
                    blocks.append('\n'.join(current_block))
                    current_block = []
                    in_annotation = False

        # Process each block
        for block in blocks:
            annotation = {}

            # Extract string fields
            for field in ['chapter', 'color', 'datetime', 'page', 'text', 'drawer', 'pos0', 'pos1']:
                match = re.search(rf'\["{field}"\]\s*=\s*"((?:[^"\\]|\\.)*)"', block)
                if match:
                    annotation[field] = match.group(1)

            # Extract numeric fields
            for field in ['pageno']:
                match = re.search(rf'\["{field}"\]\s*=\s*(\d+)', block)
                if match:
                    annotation[field] = int(match.group(1))

            if annotation:
                annotations.append(annotation)

        return annotations

    @staticmethod
    def _parse_doc_props(doc_props_str: str) -> Dict[str, str]:
        """Parse the doc_props section from Lua."""
        doc_props = {}

        # Extract string fields
        for field in ['authors', 'title', 'language', 'description', 'identifiers', 'series']:
            match = re.search(rf'\["{field}"\]\s*=\s*"((?:[^"\\]|\\.)*)"', doc_props_str)
            if match:
                doc_props[field] = match.group(1)

        return doc_props


class HighlightsCollector:
    """Collects highlights from all KoReader devices."""

    def __init__(self, base_path: Path):
        self.base_path = base_path
        self.books: Dict[str, Dict[str, Any]] = {}

    def collect(self):
        """Scan all device folders and collect highlights."""
        if not self.base_path.exists():
            print(f"Error: Base path {self.base_path} does not exist")
            return

        # Iterate through device folders
        for device_folder in self.base_path.iterdir():
            if not device_folder.is_dir():
                continue

            device_id = device_folder.name
            print(f"Scanning device: {device_id}")

            # Find all metadata.*.lua files
            metadata_files = list(device_folder.rglob("metadata.*.lua"))
            print(f"  Found {len(metadata_files)} metadata files")

            for metadata_file in metadata_files:
                try:
                    self._process_metadata_file(metadata_file, device_id)
                except Exception as e:
                    print(f"  Error processing {metadata_file}: {e}")

    def _process_metadata_file(self, filepath: Path, device_id: str):
        """Process a single metadata file."""
        data = LuaTableParser.parse_file(filepath)

        annotations = data.get('annotations')
        if not annotations:
            return  # No highlights in this file

        print(f"  Processing: {filepath.name} ({len(annotations)} highlights)")

        # Get book metadata
        doc_props = data.get('doc_props', {})
        book_title = doc_props.get('title', 'Unknown Title')
        book_authors = doc_props.get('authors', 'Unknown Author')
        book_id = data.get('partial_md5_checksum', str(filepath))

        # Initialize book entry if not exists
        if book_id not in self.books:
            self.books[book_id] = {
                'title': book_title,
                'authors': book_authors,
                'identifiers': doc_props.get('identifiers', ''),
                'language': doc_props.get('language', ''),
                'description': doc_props.get('description', ''),
                'file_path': data.get('doc_path', ''),
                'highlights': []
            }

        # Add highlights with device_id
        for annotation in data['annotations']:
            # Determine highlight type based on fields present
            has_color = 'color' in annotation
            has_text = 'text' in annotation and annotation.get('text', '')
            has_positions = 'pos0' in annotation and 'pos1' in annotation

            if has_color and has_text and has_positions:
                highlight_type = 'highlight'
            elif has_color and has_positions and not has_text:
                highlight_type = 'highlight_empty'
            elif has_color and not has_positions:
                highlight_type = 'highlight_no_position'
            elif not has_color and has_text:
                highlight_type = 'bookmark'
            else:
                highlight_type = 'unknown'

            highlight = {
                'highlight_type': highlight_type,
                'text': annotation.get('text', ''),
                'chapter': annotation.get('chapter', ''),
                'page_number': annotation.get('pageno', 0),
                'datetime': annotation.get('datetime', ''),
                'color': annotation.get('color', ''),
                'drawer': annotation.get('drawer', ''),
                'device_id': device_id,
                'page_xpath': annotation.get('page', ''),
            }
            self.books[book_id]['highlights'].append(highlight)

    def export_json(self, output_path: Path):
        """Export collected highlights to JSON."""
        # Convert to list and sort highlights by datetime
        books_list = []
        for book_id, book_data in self.books.items():
            # Sort highlights by datetime
            book_data['highlights'].sort(key=lambda x: x.get('datetime', ''))

            # Add book_id to output
            book_data['book_id'] = book_id
            books_list.append(book_data)

        # Sort books by title
        books_list.sort(key=lambda x: x.get('title', '').lower())

        output = {
            'generated_at': datetime.now().isoformat(),
            'total_books': len(books_list),
            'total_highlights': sum(len(book['highlights']) for book in books_list),
            'books': books_list
        }

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2, ensure_ascii=False)

        print(f"\nExported {output['total_highlights']} highlights from {output['total_books']} books")
        print(f"Output file: {output_path}")

    def print_summary(self):
        """Print a summary of collected highlights."""
        print(f"\n{'='*60}")
        print(f"Total books: {len(self.books)}")
        total_highlights = sum(len(book['highlights']) for book in self.books.values())
        print(f"Total highlights: {total_highlights}")
        print(f"{'='*60}")


def cmd_collect(args):
    """Handle the collect subcommand."""
    print(f"KoReader Highlights Collector")
    print(f"{'='*60}")
    print(f"Base path: {args.base_path}")
    print(f"Output file: {args.output}")
    print(f"{'='*60}\n")

    collector = HighlightsCollector(args.base_path)
    collector.collect()
    collector.print_summary()
    collector.export_json(args.output)


def main():
    parser = argparse.ArgumentParser(
        description='KoReader Highlights Collector - Manage and collect KoReader highlights',
        epilog='Use "%(prog)s <command> --help" for more information on a command.'
    )

    subparsers = parser.add_subparsers(
        title='commands',
        description='Available commands',
        dest='command',
        required=True
    )

    # Collect subcommand
    collect_parser = subparsers.add_parser(
        'collect',
        help='Collect highlights from KoReader devices',
        description='Scan syncthing folders and collect all KoReader highlights into a JSON file'
    )
    collect_parser.add_argument(
        '--base-path',
        type=Path,
        default=Path.home() / 'syncthing' / 'ebooks-highlights',
        help='Base path for syncthing highlights (default: ~/syncthing/ebooks-highlights)'
    )
    collect_parser.add_argument(
        '--output',
        type=Path,
        default=Path('highlights.json'),
        help='Output JSON file path (default: highlights.json)'
    )
    collect_parser.set_defaults(func=cmd_collect)

    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
