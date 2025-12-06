# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

KoReader Highlights Collector - A Python tool that collects and aggregates highlights from KoReader e-reader devices synced via Syncthing.

## Architecture

The project consists of a single Python script (`collect_highlights.py`) that:

1. **Scans** multiple device folders in `~/syncthing/ebooks-highlights/`
2. **Parses** KoReader Lua metadata files (`metadata.epub.lua`, `metadata.pdf.lua`)
3. **Extracts** highlights with metadata (text, chapter, page number, datetime, device ID)
4. **Aggregates** highlights grouped by book
5. **Exports** to a single JSON file (`highlights.json`)

### Key Components

- `LuaTableParser`: Custom parser for KoReader's Lua metadata format
  - `parse_file()`: Main entry point for parsing Lua files
  - `_extract_field_value()`: Brace-matching algorithm to extract nested Lua table values
  - `_parse_annotations()`: Extracts individual highlight entries
  - `_parse_doc_props()`: Extracts book metadata (title, author, etc.)

- `HighlightsCollector`: Main orchestrator
  - `collect()`: Scans all device folders and processes metadata files
  - `_process_metadata_file()`: Processes a single metadata file
  - `export_json()`: Outputs aggregated data to JSON

### File Structure

- KoReader creates `.sdr` folders alongside ebooks containing `metadata.{epub|pdf}.lua` files
- Each metadata file contains:
  - `annotations[]`: Array of highlights/bookmarks with text, datetime, chapter, page number
  - `doc_props{}`: Book metadata (title, authors, identifiers, language)
  - `partial_md5_checksum`: Unique book identifier

### Annotation Types

The parser classifies annotations into four types based on field presence:

1. **`highlight`**: Has `color`, `drawer`, `pos0`, `pos1`, and `text` - Standard text highlight
2. **`bookmark`**: No `color` field, has `text` (format: "in [Chapter Name]") - Location bookmark
3. **`highlight_empty`**: Has `color` and position fields but no `text` - Empty highlight selection
4. **`highlight_no_position`**: Has `color` but no `pos0`/`pos1` or `page` - Highlight without position data

Classification logic in `collect_highlights.py:215-229`

## Usage

```bash
# Collect highlights (~/syncthing/ebooks-highlights -> highlights.json)
python3 collect_highlights.py collect

# Publish to Karakeep
python3 collect_highlights.py publish

# View available commands
python3 collect_highlights.py --help
```

The script uses a subcommand structure. Available commands:
- `collect`: Collect and aggregate highlights from KoReader devices
- `publish`: Publish highlights to Karakeep with automatic tagging

## Karakeep Integration

### Architecture

The `publish` command pushes collected highlights to Karakeep:

1. **Loads** highlights from JSON file (output from `collect` command)
2. **Filters** only `highlight` type (excludes bookmarks and empty highlights)
3. **Authenticates** with Karakeep API using Bearer token (JWT)
4. **Resolves list name** to internal ID (accepts human-readable name or ID)
5. **Checks duplicates** by searching for existing bookmarks with same text
6. **Creates tags** if they don't exist (`book:Title`, `device:ID`)
7. **Creates bookmark** with type "text" and metadata as note
8. **Attaches tags** to bookmark
9. **Adds to list** (default: "Book Quotes", resolved to internal ID)

### Key Components

- **`KarakeepClient`** (`collect_highlights.py:304-488`): HTTP client for Karakeep API
  - `authenticate()`: Login and get JWT Bearer token
  - `search_bookmarks(query)`: Search for existing bookmarks (duplicate detection)
  - `get_all_tags()`: Fetch all tags as dict{name: id}
  - `create_tag(name)`: Create new tag if doesn't exist
  - `ensure_tag(name)`: Get or create tag using local cache
  - `create_bookmark(text, note)`: Create text-type bookmark
  - `attach_tags(bookmark_id, tag_ids)`: Attach multiple tags
  - `get_all_lists()`: Fetch all lists
  - `find_list_by_name(name)`: Find list by human-readable name (case-insensitive)
  - `get_list(list_id)`: Get list details by ID
  - `add_bookmark_to_list(list_id, bookmark_id)`: Add bookmark to a list

- **`cmd_publish()`** (`collect_highlights.py:465-611`): Main publish logic
  - Filters highlights by type (`highlight` only)
  - Implements duplicate prevention via search
  - Batch processes with progress indicators
  - Creates metadata note in JSON format with book/chapter/page info

### Karakeep API Details

- **Base URL**: `http://192.168.100.230:23001/api/v1/`
- **Authentication**: POST `/users/signin` → Bearer token
- **Endpoints used**:
  - `GET /bookmarks/search?q=query` - Search bookmarks
  - `GET /tags` - List all tags
  - `POST /tags` - Create tag with `{"name": "tagname"}`
  - `POST /bookmarks` - Create bookmark with `{"type": "text", "text": "...", "note": "..."}`
  - `POST /bookmarks/:id/tags` - Attach tags with `{"tagIds": [...]}`
  - `GET /lists` - Get all lists (for name resolution)
  - `GET /lists/:id` - Get list details by ID
  - `PUT /lists/:id/bookmarks/:bookmarkId` - Add bookmark to list

### Configuration

Credentials loaded from `.env` file:
```
KARAKEEP_ID='email@example.com'
KARAKEEP_PASSWORD='password'
KARAKEEP_URL='http://192.168.100.230:23001'  # Optional
```

### Duplicate Prevention

Uses search-based deduplication:
1. Search Karakeep for first 50 chars of highlight text
2. Check if results have matching `book:{title}` tag
3. Skip if duplicate found (unless `--force` flag used)

Alternative: Could track published highlights in local JSON file for more reliable detection.

## Dependencies

Python 3.x with standard library only (no external packages required).

## Authentication Debugging (UNRESOLVED)

### Issue
Authentication fails with HTTP 401 when attempting to publish highlights to Karakeep.

### Attempts Made

Tried multiple endpoint variations:
1. `POST /api/v1/users/signin` with `{"email": "...", "password": "..."}` → **401 Unauthorized**
2. `POST /api/v1/auth/signin` with `{"email": "...", "password": "..."}` → **404 Not Found**
3. `POST /users/signin` (no /api prefix) with `{"email": "...", "password": "..."}` → **404 Not Found**
4. `POST /api/users/signin` with `{"email": "...", "password": "..."}` → **404 Not Found**
5. `POST /api/auth/signin` with `{"email": "...", "password": "..."}` → **302 Redirect** (possibly web form)

### Findings

From the error page HTML response, the actual Karakeep API configuration shows:
- Public API URL: `http://192.168.100.230:23001/api`
- Server version: 0.27.1
- Auth configured: `disableSignups: false, disablePasswordAuth: false`

From Karakeep documentation research:
- API uses "Bearer Auth" with JWT tokens
- Documentation at https://docs.karakeep.app/API/karakeep-api/ mentions Bearer JWT authentication
- CLI tool uses API keys (not email/password), obtained from settings
- No explicit signin endpoint documented in the available API docs

### Next Steps to Debug

1. **TODO: Use official Python Karakeep library instead of custom HTTP client**:
   - Check if there's a `karakeep` or `karakeep-python` package on PyPI
   - This would handle authentication properly and avoid reverse-engineering the API
   - Update `requirements.txt` to include the library
   - Refactor `KarakeepClient` to use the official library instead of urllib

2. **Check if API key authentication required instead of email/password**:
   - Look for "API Key" or "API Token" in Karakeep web UI settings
   - Try using API key in Authorization header instead of signin endpoint

3. **Try username field instead of email**:
   ```bash
   curl -X POST http://192.168.100.230:23001/api/v1/users/signin \
     -H "Content-Type: application/json" \
     -d '{"username":"ktvkvinaykeerthi@gmail.com","password":"09022023"}'
   ```

4. **Check Karakeep logs** for actual endpoint being called and expected format

5. **Verify credentials** by logging into web UI at http://192.168.100.230:23001

6. **Check Karakeep GitHub repo** for API authentication examples or tests

7. **Try different API versions** - maybe `/api/v2/` or just `/api/`

### Current Code Location

Authentication implementation: `collect_highlights.py:351-364` (KarakeepClient.authenticate method)

## Notes

- The parser uses a custom brace-matching algorithm to handle nested Lua table structures
- Books are identified by `partial_md5_checksum` to merge highlights from same book across devices
- Device ID is extracted from the folder name (e.g., `boox-palma`, `s24u`)
- Designed to be run as a cron job for periodic collection
