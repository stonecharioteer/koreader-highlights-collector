# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

KoReader Highlights Collector - A Flask web application that collects, aggregates, and exports highlights from KoReader e-reader devices synced via Syncthing.

## Architecture

The project consists of:

**Legacy CLI** (`collect_highlights.py`) - Original JSON export script (still functional but superseded by web app)

**Flask Web Application** - Primary interface:

1. **Scans** device folders via Celery background tasks
2. **Parses** KoReader Lua metadata files using `core/parser.py`
3. **Stores** in PostgreSQL with device tracking and metadata enrichment (Open Library)
4. **Displays** via Flask UI with search, filtering, sorting, and quote image export
5. **Exports** selected highlights to customizable blog post formats (Jinja2 templates)

### Key Components

**Core Library** (`core/`)
- `LuaTableParser`: Custom parser for KoReader's Lua metadata format
  - `parse_file()`: Main entry point for parsing Lua files
  - `_extract_field_value()`: Brace-matching algorithm to extract nested Lua table values
  - `_parse_annotations()`: Extracts individual highlight entries
  - `_parse_doc_props()`: Extracts book metadata (title, author, etc.)
  - `_unescape_lua_string()`: Handles escape sequences in Lua strings

**Flask Application** (`app/`)
- `app/views/books.py`: Book listing, detail, metadata editing, Open Library integration
- `app/views/exports.py`: Template management, export job creation, download, deletion
- `app/views/config.py`: Source folder configuration, Open Library identity
- `app/views/tasks.py`: Trigger background scans

**Background Tasks** (`tasks.py`)
- `scan_all_paths()`: Scans all configured source folders
- `import_file(path)`: Parses metadata file and upserts to database
- `export_highlights(job_id)`: Renders Jinja2 template, creates ZIP with markdown + cover

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

**Web Application** (Primary)
```bash
docker compose up --build
# Visit http://localhost:48138
```

**Legacy CLI** (Still available)
```bash
# Collect highlights (~/syncthing/ebooks-highlights -> highlights.json)
python3 collect_highlights.py collect

# Publish to Karakeep
python3 collect_highlights.py publish
```

## Export Feature

The web application includes a comprehensive export system for creating blog posts from highlights:

### Workflow
1. Open any book detail page → Click **Select** button
2. Check desired highlights (Select All / Deselect All available)
3. Click **Export Selected** → Job queued in Celery
4. Navigate to **Exports → Export Jobs** to monitor progress
5. Page auto-refreshes; download ZIP when completed
6. Extract ZIP: `export.md` (rendered markdown) + `cover.jpg` (book cover)
7. Copy markdown to blog, edit "Thoughts" section
8. Delete job from UI to free disk space

### Export Templates (`app/views/exports.py`, `app/models.py`)

**Database Models**
- `ExportTemplate`: Stores Jinja2 templates with `name`, `template_content`, `is_default`
- `ExportJob`: Tracks async jobs with `job_id` (UUID), `book_id`, `template_id`, `highlight_ids` (JSON), `status`, `file_path`

**Template Management**
- Templates UI: Create/edit/delete custom templates
- Default Hugo template included (matches stonecharioteer.com format)
- Help dialog documents all available Jinja2 variables
- Set one template as default for quick exports

**Available Template Variables**
- **Book**: `book.clean_title`, `book.raw_title`, `book.clean_authors`, `book.raw_authors`, `book.description`, `book.language`
- **Highlights**: Loop over `highlights` array with `highlight.text`, `highlight.chapter`, `highlight.page_number`, `highlight.datetime`
- **Reading Dates**: `read_start`, `read_end` (derived from first/last highlight timestamps)
- **Export Metadata**: `current_date` (YYYY-MM-DD), `current_timestamp` (YYYY-MM-DD HH:MM:SS)
- **Jinja Utilities**: `loop.index`, conditionals, filters, `{% if %}`, `{% for %}`

**Celery Task** (`tasks.py:export_highlights`)
1. Load ExportJob by `job_id`
2. Fetch Book, ExportTemplate, selected Highlights from database
3. Calculate `read_start`/`read_end` from highlight datetimes
4. Render Jinja2 template with context
5. Create ZIP file:
   - `export.md`: Rendered markdown content
   - `cover.jpg` or `cover.png`: Book cover from database blob (if available)
6. Store ZIP in `EXPORT_DIR` (configurable via env var, default `/tmp/exports`)
7. Update job status: `pending` → `processing` → `completed` or `failed`

**Job Management**
- Jobs list page shows all exports with status badges
- Individual delete button per job (removes DB record + ZIP file)
- "Delete All" button for bulk cleanup
- Confirmation dialogs prevent accidental deletion

### Example: Hugo Blog Template

Default template generates Hugo-compatible markdown:

```markdown
---
date: '2025-12-07 10:30:00'
draft: false
title: 'GN Devy - Mahabharata: The Epic and the Nation'
tags:
    - "reading"
cover:
  image: "/images/books/mahabharata-the-epic-and-the-nation.jpg"
ShowToc: true
---

## Thoughts

[Add your thoughts about the book here]

## Highlights

### 1. The Epic Quest

#### Page 37 @ 20 April 2025 09:29:36 PM

> *It took the scholars at the Bhandarkar Institute...*

### 2. The Wheel

#### Page 109 @ 20 April 2025 10:36:01 PM

> *The widespread misconception...*
```

Template automatically:
- Groups highlights by chapter (new heading when chapter changes)
- Formats timestamps in human-readable format
- Generates lowercase-hyphenated slugs for image paths
- Includes Hugo frontmatter with proper YAML formatting

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
