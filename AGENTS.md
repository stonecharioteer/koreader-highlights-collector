# Repository Guidelines

## Project Overview

KoReader Highlights Collector - A Flask web application that collects, aggregates, and exports highlights from KoReader e-reader devices synced via Syncthing.

### Architecture

The project consists of:

**Flask Web Application** (Primary)
1. Scans device folders via Celery background tasks
2. Parses KoReader Lua metadata files using `core/parser.py`
3. Stores in PostgreSQL with device tracking and metadata enrichment (Open Library)
4. Displays via Flask UI with search, filtering, sorting, and quote image export
5. Exports selected highlights to customizable blog post formats (Jinja2 templates)

**Legacy CLI** (`collect_highlights.py`) - Original JSON export script (still functional, includes Karakeep integration)

## Project Structure & Module Organization

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
- `app/models.py`: SQLAlchemy models (Book, Highlight, ExportTemplate, ExportJob, etc.)
- `app/templates/`: Jinja2 templates (layout.html, books/*.html, config/*.html, exports/*.html)
- `app/static/`: Bootstrap CSS/JS, html2canvas.min.js

**Background Tasks** (`tasks.py`)
- `scan_all_paths()`: Scans all configured source folders
- `import_file(path)`: Parses metadata file and upserts to database
- `export_highlights(job_id)`: Renders Jinja2 template, creates ZIP with markdown + cover

**Configuration**
- `docker-compose.yml`: Services (db, rabbitmq, web, worker)
- `.env`: Local credentials (Karakeep, database, etc.) - do not commit
- `pyproject.toml`: Dependencies via uv
- `docs/ARCHITECTURE.md`: Detailed system design
- `README.md`: User-facing documentation

## File Structure

- KoReader creates `.sdr` folders alongside ebooks containing `metadata.{epub|pdf}.lua` files
- Each metadata file contains:
  - `annotations[]`: Array of highlights/bookmarks with text, datetime, chapter, page number
  - `doc_props{}`: Book metadata (title, authors, identifiers, language)
  - `partial_md5_checksum`: Unique book identifier

### Annotation Types

The parser classifies annotations into four types:

1. **`highlight`**: Standard text highlight with `color`, `drawer`, `pos0`, `pos1`, and `text`
2. **`bookmark`**: Location bookmark with `text` (format: "in [Chapter Name]"), no `color`
3. **`highlight_empty`**: Empty highlight selection with `color` and position but no `text`
4. **`highlight_no_position`**: Highlight with `color` but no `pos0`/`pos1` or `page`

## Build, Test, and Development Commands

**Docker (Primary)**
```bash
docker compose up --build              # Start all services
docker compose logs web --tail 50      # View web logs
docker compose restart web             # Restart web service
docker compose exec web python <cmd>   # Run Python in container
```

**Local Development (uv)**
```bash
uv sync                                # Install dependencies
uv run flask --app app run --debug     # Run Flask dev server
uv run celery -A tasks.celery worker -l info  # Run Celery worker
uv run pytest                          # Run tests
```

**Legacy CLI**
```bash
python3 collect_highlights.py collect --base-path ~/syncthing/ebooks-highlights
python3 collect_highlights.py publish --list-name "Book Quotes" --dry-run
```

## Export Feature

The web application includes a comprehensive export system for creating blog posts:

### Workflow
1. Open book detail page → Click **Select** button
2. Check desired highlights (Select All / Deselect All available)
3. Click **Export Selected** → Job queued in Celery
4. Navigate to **Exports → Export Jobs** to monitor progress
5. Page auto-refreshes; download ZIP when completed
6. Extract ZIP: `export.md` (rendered markdown) + `cover.jpg` (book cover)
7. Copy markdown to blog, edit "Thoughts" section
8. Delete job from UI to free disk space

### Export Templates

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

**Celery Task Flow** (`tasks.py:export_highlights`)
1. Load ExportJob by `job_id`
2. Fetch Book, ExportTemplate, selected Highlights from database
3. Calculate `read_start`/`read_end` from highlight datetimes
4. Render Jinja2 template with context
5. Create ZIP file: `export.md` (rendered markdown) + `cover.jpg/png` (book cover blob)
6. Store ZIP in `EXPORT_DIR` (env var, default `/tmp/exports`)
7. Update job status: `pending` → `processing` → `completed` or `failed`

**Job Management**
- Jobs list page shows all exports with status badges
- Individual delete button per job (removes DB record + ZIP file)
- "Delete All" button for bulk cleanup
- Confirmation dialogs prevent accidental deletion

## Coding Style & Naming Conventions

- Python 3.11+; follow PEP 8 (4-space indents, 100-120 col soft limit)
- Use snake_case for functions/vars, PascalCase for classes, UPPER_SNAKE_CASE for constants
- Prefer `pathlib.Path` for I/O and add type hints (`typing`) where beneficial
- Flask blueprints for modularity; SQLAlchemy for models
- Jinja2 templates with Bootstrap 5 for UI
- Keep components single-purpose; refactor into services/helpers as needed

## Testing Guidelines

- Framework: `pytest` (tests go in `tests/` directory with `test_*.py` naming)
- Priority areas:
  - Lua parsing (`LuaTableParser`) with edge cases
  - Export template rendering (Jinja2)
  - Celery task execution (mock external services)
  - Flask routes (use test client)
- Example: `uv run pytest -v` or `docker compose exec web pytest`
- Aim to cover common metadata edge cases (missing fields, empty highlights, bookmarks without text)

## Commit & Pull Request Guidelines

- Commit style: Conventional Commits (e.g., `feat:`, `fix:`, `docs:`, `chore:`)
- Write imperative, concise messages
- PRs should include:
  - Summary of changes
  - Rationale
  - Screenshots/logs when modifying UI or output
  - Links to issues (if any)
- Checklist:
  - No secrets in diffs
  - Updated `README.md`/docs as needed
  - Basic smoke test verified (web UI loads, export works)
  - Migrations included if schema changed

## Security & Configuration Tips

- Keep `.env` local and untracked; never log credentials
- Use `--dry-run` when validating CLI changes
- Network calls use `urllib` (CLI) or `requests` (web); handle exceptions gracefully
- For local paths, prefer `~` or environment variables; avoid hardcoding device-specific paths
- PostgreSQL images stored as blobs (BYTEA); no external image storage needed
- Export files in `EXPORT_DIR` should be cleaned up by users via UI

## Environment Variables

- `DATABASE_URL`: PostgreSQL connection string
- `RABBITMQ_URL`: RabbitMQ broker URL
- `HIGHLIGHTS_BASE_PATH`: Base path for KoReader metadata files
- `EXPORT_DIR`: Directory for export ZIP files (default `/tmp/exports`)
- `FLASK_ENV`: `development` or `production`
- `SECRET_KEY`: Flask session secret
- `KARAKEEP_ID`, `KARAKEEP_PASSWORD`, `KARAKEEP_URL`: Legacy CLI credentials

## Notes

- The parser uses a custom brace-matching algorithm to handle nested Lua table structures
- Books are identified by `partial_md5_checksum` to merge highlights from same book across devices
- Device ID is extracted from the folder name (e.g., `boox-palma`, `s24u`) or configured label
- Web app designed for LAN access (no authentication); use behind firewall or VPN
- Export feature enables blog post creation workflow: select → export → download → copy → delete
- Default Hugo template matches stonecharioteer.com format (chapter grouping, frontmatter, human dates)
