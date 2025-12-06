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

  DB[(Postgres)]
  MQ[(RabbitMQ)]
  RFS[(RustFS
  Image Store)]
  FS[/Source Folders\n(sample-highlights, devices)/]
  OL[(Open Library API)]

  BROWSER -->|HTTP :48138| WEB
  WEB -->|SQL| DB
  WEB -->|AMQP enqueue| MQ
  CELERY -->|AMQP consume| MQ
  CELERY -->|SQL| DB
  CELERY -->|read-only scan| FS
  CELERY --> CORE
  CELERY -->|HTTP fetch| OL
  WEB -->|HTTP store/serve| RFS
  CELERY -->|HTTP store| RFS

  note right of FS
    metadata.*.lua files
    per device folders
    read-only mount
  end

  classDef store fill:#eef,stroke:#99c
  classDef ext fill:#ffe,stroke:#cc9
  class DB,MQ,RFS store
  class OL ext
```

## Components
- Flask Web App: Serves pages to browse and edit metadata; no auth (LAN only).
- Core Library (`core/`): Parsing/collection logic and pure utilities; easy to unit test.
- Celery Worker: Background tasks to read KoReader metadata and populate DB.
- Postgres: Primary persistence for cleaned data and relationships.
- RabbitMQ: Broker for Celery tasks.
- RustFS: Local image store for book cover thumbnails.

## Data Flow
+ Source (read-only): KoReader metadata files (e.g., `metadata.*.lua`) under `HIGHLIGHTS_BASE_PATH`.
+ Import: Celery scans paths → `core` parses → upsert into DB (no writes to source files).
+ Manage: Flask UI edits cleaned fields (title, author, cover), searches Open Library and applies results, and merges highlights.

## Models (SQLAlchemy)
- Book: id, raw_title, raw_authors, clean_title, clean_authors, external_url (stored in `goodreads_url`), image_url, identifiers, language, created_at, updated_at.
- Highlight: id, book_id, text, chapter, page_number, datetime, color, device_id, page_xpath, kind, created_at.
- HighlightDevice: id, highlight_id, device_id (unique per highlight).
- Note: id, book_id, text, datetime, device_id, created_at.
- Bookmark: id, book_id, chapter, page_number, datetime, device_id, created_at.
- MergedHighlight: id, book_id, text, notes (optional), created_at.
- MergedHighlightItem: merged_id, highlight_id (preserve originals; mark as merged via relation).
- SourcePath: id, path, enabled, device_label.
- AppConfig: id, ol_app_name, ol_contact_email.
  - Also `rustfs_url` to configure image store endpoint.

## Flask Structure
- app/
  - __init__.py (factory + config)
  - views/
    - books.py (list, detail, edit inline, OL search/apply, merge UI, refresh)
    - tasks.py (trigger rescan)
    - config.py (manage folders + Open Library identity)
  - templates/
    - layout.html, books/*.html, config/*.html
  - static/ (Bootstrap CSS/JS vendored or CDN)

## Celery
- `celery_app.py` with factory using Flask config.
- Tasks: `scan_all_paths()`, `scan_base_path(path)`, `import_file(path)`.
- Dedupe highlights per book by (text, page_number, kind in highlight variants) and attach device tags.
 - When applying Open Library metadata, attempt to persist cover images to RustFS and store the returned local URL.

## Configuration
- Env vars: `DATABASE_URL`, `HIGHLIGHTS_BASE_PATH`, `RABBITMQ_URL`.
- In-app config for source folders (with device labels) and Open Library App Name + Contact Email (used for User-Agent).
- In-app config for RustFS base URL; web uses this to store and serve cover images.
- `.env` for local compose; secrets not committed.

## Non-goals
- Do not modify any KoReader files or JSON outputs; DB is the system of record for cleaned/merged data.

## Deployment
- Docker: multi-stage build generates `requirements.txt` from `pyproject.toml` via pip-compile, then installs with pip.
- Port: web binds to 48138; exposed as `48138:48138` in compose.
- Compose services: `db`, `rabbitmq`, `web`, `worker`, `rustfs`. The app reads `RUSTFS_URL` (e.g., http://rustfs:8080).
