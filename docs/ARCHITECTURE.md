# Architecture Overview

## Components
- Flask Web App: Serves pages to browse and edit metadata; no auth (LAN only).
- Core Library (`core/`): Parsing/collection logic and pure utilities; easy to unit test.
- Celery Worker: Background tasks to read KoReader metadata and populate DB.
- Postgres: Primary persistence for cleaned data and relationships.
- RabbitMQ: Broker for Celery tasks.

## Data Flow
+ Source (read-only): KoReader metadata files (e.g., `metadata.*.lua`) under `HIGHLIGHTS_BASE_PATH`.
+ Import: Celery scans paths → `core` parses → upsert into DB (no writes to source files).
+ Manage: Flask UI edits cleaned fields (title, author, Goodreads URL/image) and merges highlights.

## Models (SQLAlchemy)
- Book: id, raw_title, raw_authors, clean_title, clean_authors, goodreads_url, image_url, identifiers, language, created_at, updated_at.
- Highlight: id, book_id, text, chapter, page_number, datetime, color, device_id, page_xpath, created_at.
- Note: id, book_id, text, datetime, device_id, created_at.
- Bookmark: id, book_id, chapter, page_number, datetime, device_id, created_at.
- MergedHighlight: id, book_id, text, notes (optional), created_at.
- MergedHighlightItem: merged_id, highlight_id (preserve originals; mark as merged via relation).

## Flask Structure
- app/
  - __init__.py (factory + config)
  - views/
    - books.py (list, edit, detail)
    - highlights.py (merge UI, actions)
    - tasks.py (trigger rescan)
  - templates/
    - layout.html, books/*.html, highlights/*.html
  - static/ (Bootstrap CSS/JS vendored or CDN)

## Celery
- `celery_app.py` with factory using Flask config.
- Tasks: `scan_files(base_path)`, `import_file(path)`, `enrich_goodreads(book_id)`.
- Idempotent upserts keyed by checksum/device+path.

## Configuration
- Env vars: `DATABASE_URL`, `HIGHLIGHTS_BASE_PATH`, `RABBITMQ_URL`.
- `.env` for local compose; secrets not committed.

## Non-goals
- Do not modify any KoReader files or JSON outputs; DB is the system of record for cleaned/merged data.
