# Architecture Overview

## Diagram

```mermaid
flowchart LR
  subgraph Client
    BROWSER[User Browser]
  end

  subgraph App[Flask Application]
    WEB[Flask Web
    - books/config/views]
    CORE[(core/ parser
    + collector)]
  end

  subgraph Worker[Background]
    CELERY[Celery Worker]
  end

  DB[(Postgres
  + Image Blobs)]
  MQ[(RabbitMQ)]
  FS[/Source Folders\n(sample-highlights, devices)/]
  OL[(Open Library API)]

  BROWSER -->|HTTP :48138| WEB
  WEB -->|SQL + serve images| DB
  WEB -->|AMQP enqueue| MQ
  CELERY -->|AMQP consume| MQ
  CELERY -->|SQL| DB
  CELERY -->|read-only scan| FS
  CELERY --> CORE
  CELERY -->|HTTP fetch| OL
  WEB -->|HTTP fetch images| OL

  note right of FS
    metadata.*.lua files
    per device folders
    read-only mount
  end

  classDef store fill:#eef,stroke:#99c
  classDef ext fill:#ffe,stroke:#cc9
  class DB,MQ store
  class OL ext
```

## Components
- Flask Web App: Serves pages to browse and edit metadata; no auth (LAN only).
- Core Library (`core/`): Parsing/collection logic and pure utilities; easy to unit test.
- Celery Worker: Background tasks to read KoReader metadata and populate DB.
- Postgres: Primary persistence for cleaned data, relationships, and book cover images (stored as binary blobs).
- RabbitMQ: Broker for Celery tasks.

## Data Flow
+ Source (read-only): KoReader metadata files (e.g., `metadata.*.lua`) under `HIGHLIGHTS_BASE_PATH`.
+ Import: Celery scans paths → `core` parses → upsert into DB (no writes to source files).
+ Manage: Flask UI edits cleaned fields (title, author, cover), searches Open Library and applies results, and merges highlights.
+ Images: Flask fetches cover images from external URLs (e.g., Open Library), stores them as binary blobs in Postgres (`image_data`, `image_content_type`), and serves them directly from the database.

## Models (SQLAlchemy)
- Book: id, raw_title, raw_authors, clean_title, clean_authors, external_url (stored in `goodreads_url`), image_url (deprecated), image_data (BYTEA blob), image_content_type, identifiers, language, created_at, updated_at.
- Highlight: id, book_id, text, chapter, page_number, datetime, color, device_id, page_xpath, kind, created_at.
- HighlightDevice: id, highlight_id, device_id (unique per highlight).
- Note: id, book_id, text, datetime, device_id, created_at.
- Bookmark: id, book_id, chapter, page_number, datetime, device_id, created_at.
- MergedHighlight: id, book_id, text, notes (optional), created_at.
- MergedHighlightItem: merged_id, highlight_id (preserve originals; mark as merged via relation).
- SourcePath: id, path, enabled, device_label.
- AppConfig: id, ol_app_name, ol_contact_email, rustfs_url (deprecated, no longer used).

## Flask Structure
- app/
  - __init__.py (factory + config)
  - views/
    - books.py (list, detail, edit inline, OL search/apply, merge UI, refresh, image upload/fetch, cover serving)
    - tasks.py (trigger rescan)
    - config.py (manage folders + Open Library identity)
  - services/
    - imagestore.py (fetch images from URLs)
    - openlibrary.py (API integration)
  - templates/
    - layout.html, books/*.html, config/*.html
  - static/ (Bootstrap CSS/JS vendored or CDN, html2canvas.min.js)

## Celery
- `celery_app.py` with factory using Flask config.
- Tasks: `scan_all_paths()`, `scan_base_path(path)`, `import_file(path)`.
- Dedupe highlights per book by (text, page_number, kind in highlight variants) and attach device tags.

## Configuration
- Env vars: `DATABASE_URL`, `HIGHLIGHTS_BASE_PATH`, `RABBITMQ_URL`, `FLASK_ENV`.
- In-app config for source folders (with device labels) and Open Library App Name + Contact Email (used for User-Agent).
- `.env` for local compose; secrets not committed.

## Non-goals
- Do not modify any KoReader files or JSON outputs; DB is the system of record for cleaned/merged data.

## Deployment
- Docker: multi-stage build generates `requirements.txt` from `pyproject.toml` via pip-compile, then installs with pip.
- Port: web binds to 48138; exposed as `48138:48138` in compose.
- Compose services: `db`, `rabbitmq`, `web`, `worker`.
- Images are stored as binary blobs (BYTEA) directly in PostgreSQL, eliminating the need for external image storage services.
