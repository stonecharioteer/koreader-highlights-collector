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
from typing import Dict, List, Any, Optional
from datetime import datetime
import argparse
import urllib.request
import urllib.parse
import urllib.error


def load_env_file(env_path: Path = None) -> Dict[str, str]:
    """Load environment variables from .env file."""
    if env_path is None:
        env_path = Path(__file__).parent / '.env'

    env_vars = {}
    if not env_path.exists():
        return env_vars

    with open(env_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                # Remove quotes if present
                value = value.strip().strip('"').strip("'")
                env_vars[key] = value

    return env_vars


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


class KarakeepClient:
    """Client for interacting with Karakeep API."""

    def __init__(self, base_url: str, email: str, password: str):
        self.base_url = base_url.rstrip('/')
        self.email = email
        self.password = password
        self.token: Optional[str] = None
        self.tag_cache: Dict[str, str] = {}  # name -> id

    def _make_request(
        self,
        endpoint: str,
        method: str = 'GET',
        data: Optional[Dict] = None,
        require_auth: bool = True
    ) -> Dict[str, Any]:
        """Make an HTTP request to Karakeep API."""
        url = f"{self.base_url}/api/v1{endpoint}"

        headers = {
            'Content-Type': 'application/json',
        }

        if require_auth and self.token:
            headers['Authorization'] = f'Bearer {self.token}'

        req_data = json.dumps(data).encode('utf-8') if data else None

        request = urllib.request.Request(
            url,
            data=req_data,
            headers=headers,
            method=method
        )

        try:
            with urllib.request.urlopen(request) as response:
                response_data = response.read().decode('utf-8')
                return json.loads(response_data) if response_data else {}
        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8')
            raise Exception(f"HTTP {e.code} error: {error_body}")
        except Exception as e:
            raise Exception(f"Request failed: {e}")

    def authenticate(self) -> bool:
        """Authenticate with Karakeep and get Bearer token."""
        try:
            response = self._make_request(
                '/users/signin',
                method='POST',
                data={'email': self.email, 'password': self.password},
                require_auth=False
            )
            self.token = response.get('token')
            return bool(self.token)
        except Exception as e:
            print(f"Authentication failed: {e}")
            return False

    def search_bookmarks(self, query: str) -> List[Dict[str, Any]]:
        """Search for bookmarks matching query."""
        try:
            encoded_query = urllib.parse.quote(query)
            response = self._make_request(f'/bookmarks/search?q={encoded_query}')
            return response.get('bookmarks', [])
        except Exception as e:
            print(f"Search failed: {e}")
            return []

    def get_all_tags(self) -> Dict[str, str]:
        """Get all tags and return as dict of name -> id."""
        try:
            response = self._make_request('/tags')
            tags = response.get('tags', [])
            return {tag['name']: tag['id'] for tag in tags}
        except Exception as e:
            print(f"Failed to get tags: {e}")
            return {}

    def create_tag(self, name: str) -> Optional[str]:
        """Create a new tag and return its ID."""
        try:
            response = self._make_request(
                '/tags',
                method='POST',
                data={'name': name}
            )
            return response.get('id')
        except Exception as e:
            print(f"Failed to create tag '{name}': {e}")
            return None

    def ensure_tag(self, name: str) -> Optional[str]:
        """Get or create a tag, using cache."""
        # Check cache first
        if name in self.tag_cache:
            return self.tag_cache[name]

        # Refresh cache from server if not found
        server_tags = self.get_all_tags()
        self.tag_cache.update(server_tags)

        if name in self.tag_cache:
            return self.tag_cache[name]

        # Create new tag
        tag_id = self.create_tag(name)
        if tag_id:
            self.tag_cache[name] = tag_id
        return tag_id

    def create_bookmark(self, text: str, note: Optional[str] = None) -> Optional[str]:
        """Create a text bookmark and return its ID."""
        try:
            data = {
                'type': 'text',
                'text': text
            }
            if note:
                data['note'] = note

            response = self._make_request(
                '/bookmarks',
                method='POST',
                data=data
            )
            return response.get('id')
        except Exception as e:
            print(f"Failed to create bookmark: {e}")
            return None

    def attach_tags(self, bookmark_id: str, tag_ids: List[str]) -> bool:
        """Attach tags to a bookmark."""
        try:
            self._make_request(
                f'/bookmarks/{bookmark_id}/tags',
                method='POST',
                data={'tagIds': tag_ids}
            )
            return True
        except Exception as e:
            print(f"Failed to attach tags: {e}")
            return False

    def get_all_lists(self) -> List[Dict[str, Any]]:
        """Get all lists."""
        try:
            response = self._make_request('/lists')
            return response.get('lists', [])
        except Exception as e:
            print(f"Failed to get lists: {e}")
            return []

    def find_list_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Find a list by its name (case-insensitive)."""
        lists = self.get_all_lists()
        name_lower = name.lower()
        for lst in lists:
            if lst.get('name', '').lower() == name_lower:
                return lst
        return None

    def get_list(self, list_id: str) -> Optional[Dict[str, Any]]:
        """Get a list by its ID."""
        try:
            return self._make_request(f'/lists/{list_id}')
        except Exception as e:
            print(f"Failed to get list: {e}")
            return None

    def add_bookmark_to_list(self, list_id: str, bookmark_id: str) -> bool:
        """Add a bookmark to a list."""
        try:
            self._make_request(
                f'/lists/{list_id}/bookmarks/{bookmark_id}',
                method='PUT'
            )
            return True
        except Exception as e:
            print(f"Failed to add bookmark to list: {e}")
            return False


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


def cmd_publish(args):
    """Handle the publish subcommand."""
    print(f"KoReader → Karakeep Publisher")
    print(f"{'='*60}")
    print(f"Input file: {args.input}")
    print(f"Karakeep URL: {args.karakeep_url}")
    print(f"List: {args.list_name}")
    print(f"Dry run: {args.dry_run}")
    print(f"{'='*60}\n")

    # Load highlights JSON
    if not args.input.exists():
        print(f"Error: Input file {args.input} not found")
        print("Run 'collect' command first to generate highlights.json")
        return

    with open(args.input, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Filter only real text highlights (not bookmarks or empty)
    highlights_to_publish = []
    for book in data['books']:
        for highlight in book['highlights']:
            if highlight['highlight_type'] == 'highlight' and highlight.get('text'):
                highlights_to_publish.append({
                    'book_title': book['title'],
                    'book_authors': book['authors'],
                    'book_id': book['book_id'],
                    'highlight': highlight
                })

    print(f"Found {len(highlights_to_publish)} highlights to publish")
    print(f"(Filtered from {data['total_highlights']} total annotations)\n")

    if len(highlights_to_publish) == 0:
        print("No highlights to publish!")
        return

    if args.dry_run:
        print("DRY RUN MODE - No changes will be made\n")
        if args.list_name:
            print(f"Highlights would be added to list: '{args.list_name}'\n")
        print("Sample highlights that would be published:")
        for i, item in enumerate(highlights_to_publish[:5], 1):
            h = item['highlight']
            print(f"\n{i}. Book: {item['book_title']}")
            print(f"   Chapter: {h['chapter']}")
            print(f"   Text: {h['text'][:80]}...")
            print(f"   Tags: book:{item['book_title']}, device:{h['device_id']}")
        print(f"\n... and {len(highlights_to_publish) - 5} more")
        return

    # Initialize Karakeep client
    client = KarakeepClient(args.karakeep_url, args.email, args.password)

    print("Authenticating with Karakeep...")
    if not client.authenticate():
        print("Failed to authenticate! Check your credentials.")
        return

    print("✓ Authenticated successfully\n")

    # Resolve list name to ID if needed
    list_id = None
    if args.list_name:
        print(f"Resolving list '{args.list_name}'...")

        # Check if it looks like an ID (alphanumeric, no spaces)
        if args.list_name.replace('_', '').replace('-', '').isalnum() and ' ' not in args.list_name:
            # Treat as ID
            list_info = client.get_list(args.list_name)
            if list_info:
                list_id = args.list_name
                list_name = list_info.get('name', 'Unknown')
                print(f"✓ Found list by ID: '{list_name}' ({list_id})\n")
            else:
                print(f"✗ List ID '{args.list_name}' not found")
        else:
            # Treat as name - search for it
            list_info = client.find_list_by_name(args.list_name)
            if list_info:
                list_id = list_info.get('id')
                list_name = list_info.get('name')
                print(f"✓ Found list: '{list_name}' ({list_id})\n")
            else:
                print(f"✗ List '{args.list_name}' not found")

        if not list_id:
            print(f"Available lists:")
            all_lists = client.get_all_lists()
            for lst in all_lists:
                print(f"  - {lst.get('name')} (ID: {lst.get('id')})")
            print("\nHighlights will be created without adding to a list.")
            print("Use --list-name with one of the above names or IDs.\n")

    # Pre-load tags cache
    print("Loading existing tags...")
    client.tag_cache = client.get_all_tags()
    print(f"✓ Found {len(client.tag_cache)} existing tags\n")

    # Publish highlights
    published_count = 0
    skipped_count = 0
    failed_count = 0

    for i, item in enumerate(highlights_to_publish, 1):
        book_title = item['book_title']
        h = item['highlight']
        text = h['text']

        # Progress indicator
        if i % 10 == 0 or i == 1:
            print(f"Processing {i}/{len(highlights_to_publish)}...")

        # Create unique identifier for duplicate check
        search_query = text[:50]  # First 50 chars

        # Check for duplicates
        existing = client.search_bookmarks(search_query)
        if existing and not args.force:
            # Check if any result has the same book tag
            book_tag_name = f"book:{book_title}"
            for bookmark in existing:
                bookmark_tags = [t['name'] for t in bookmark.get('tags', [])]
                if book_tag_name in bookmark_tags:
                    skipped_count += 1
                    continue

        # Create metadata note
        metadata = {
            'chapter': h['chapter'],
            'page': h.get('page_number', 'N/A'),
            'datetime': h['datetime'],
            'book': {
                'title': book_title,
                'authors': item['book_authors'],
                'id': item['book_id']
            },
            'device': h['device_id'],
            'color': h.get('color', ''),
            'source': 'koreader-highlights-collector'
        }
        note = json.dumps(metadata, indent=2)

        # Create bookmark
        bookmark_id = client.create_bookmark(text, note)
        if not bookmark_id:
            print(f"  ✗ Failed to create bookmark for: {text[:50]}...")
            failed_count += 1
            continue

        # Ensure and attach tags
        tag_names = [
            f"book:{book_title}",
            f"device:{h['device_id']}"
        ]

        tag_ids = []
        for tag_name in tag_names:
            tag_id = client.ensure_tag(tag_name)
            if tag_id:
                tag_ids.append(tag_id)

        if tag_ids:
            if not client.attach_tags(bookmark_id, tag_ids):
                print(f"  ! Bookmark created but failed to attach tags")

        # Add to list if specified
        if list_id:
            if not client.add_bookmark_to_list(list_id, bookmark_id):
                print(f"  ! Bookmark created but failed to add to list")

        published_count += 1

    # Print summary
    print(f"\n{'='*60}")
    print(f"SUMMARY")
    print(f"{'='*60}")
    print(f"Published: {published_count}")
    print(f"Skipped (duplicates): {skipped_count}")
    print(f"Failed: {failed_count}")
    print(f"Total processed: {len(highlights_to_publish)}")
    print(f"{'='*60}")


def main():
    # Load environment variables
    env_vars = load_env_file()

    parser = argparse.ArgumentParser(
        description='KoReader Highlights Collector - Manage and collect KoReader highlights',
        epilog='''
Examples:
  # Collect highlights from default location
  %(prog)s collect

  # Publish to Karakeep (preview first)
  %(prog)s publish --dry-run
  %(prog)s publish

  # Full workflow
  %(prog)s collect && %(prog)s publish

Use "%(prog)s <command> --help" for more information on a command.
        ''',
        formatter_class=argparse.RawDescriptionHelpFormatter
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
        description='Scan syncthing folders and collect all KoReader highlights into a JSON file',
        epilog='''
Examples:
  # Collect with default settings
  %(prog)s

  # Custom paths
  %(prog)s --base-path ~/my-highlights --output my-highlights.json

  # Dated output files
  %(prog)s --output highlights_$(date +%%Y%%m%%d).json
        ''',
        formatter_class=argparse.RawDescriptionHelpFormatter
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

    # Publish subcommand
    publish_parser = subparsers.add_parser(
        'publish',
        help='Publish highlights to Karakeep',
        description='Push collected highlights to Karakeep with automatic tagging and duplicate detection',
        epilog='''
Examples:
  # Preview what would be published (recommended first run)
  %(prog)s --dry-run

  # Publish with credentials from .env file
  %(prog)s

  # Publish specific file
  %(prog)s --input my-highlights.json

  # Force re-publish even if duplicates exist
  %(prog)s --force

Credentials:
  Set KARAKEEP_ID, KARAKEEP_PASSWORD, and optionally KARAKEEP_URL in .env file
  or use --email and --password arguments.
        ''',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    publish_parser.add_argument(
        '--input',
        type=Path,
        default=Path('highlights.json'),
        help='Input JSON file from collect command (default: highlights.json)'
    )
    publish_parser.add_argument(
        '--karakeep-url',
        type=str,
        default=env_vars.get('KARAKEEP_URL', 'http://192.168.100.230:23001'),
        help='Karakeep server URL (default: from .env or http://192.168.100.230:23001)'
    )
    publish_parser.add_argument(
        '--email',
        type=str,
        default=env_vars.get('KARAKEEP_ID'),
        help='Karakeep email/username (default: from .env KARAKEEP_ID)'
    )
    publish_parser.add_argument(
        '--password',
        type=str,
        default=env_vars.get('KARAKEEP_PASSWORD'),
        help='Karakeep password (default: from .env KARAKEEP_PASSWORD)'
    )
    publish_parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview what would be published without making changes'
    )
    publish_parser.add_argument(
        '--force',
        action='store_true',
        help='Publish even if duplicates are detected'
    )
    publish_parser.add_argument(
        '--list-name',
        type=str,
        default='Book Quotes',
        help='Karakeep list name or ID to add highlights to (default: "Book Quotes")'
    )
    publish_parser.set_defaults(func=cmd_publish)

    args = parser.parse_args()

    # Validate credentials for publish command
    if args.command == 'publish' and not args.dry_run:
        if not args.email or not args.password:
            parser.error(
                'Karakeep credentials required. Either:\n'
                '  1. Set KARAKEEP_ID and KARAKEEP_PASSWORD in .env file, or\n'
                '  2. Use --email and --password arguments'
            )

    args.func(args)


if __name__ == '__main__':
    main()
