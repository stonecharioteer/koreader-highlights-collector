# Migration Plan: CLI → Web App

## Goals
- Local Flask web app to manage highlights metadata.
- Background ingestion via Celery with RabbitMQ; persist cleaned data in DB.
- Simple Bootstrap UI to list books, edit metadata, link/thumbnail from Goodreads, and merge highlights.
- Never modify source KoReader files; read-only import into DB.
- Extract reusable parsing/collection code into a testable core library.

## Phases
1) Core library extraction
- Move parsing and collecting logic into `core/` package with pure functions and dataclasses.
- Keep CLI behavior available via thin wrappers (optional).

2) Data model & persistence
- SQLAlchemy models: `Book`, `Highlight`, `Note`, `Bookmark`, `MergedHighlight`, `MergedHighlightItem`.
- Store both raw and cleaned fields (e.g., `raw_title`, `clean_title`).
- Postgres via Docker Compose. Alembic for migrations (optional at start).

3) Web server (Flask)
- App factory, blueprints: `books`, `highlights`, `tasks`.
- Views: Book list, book detail (highlights), edit form, merge tool.
- Jinja templates + Bootstrap (no JS frameworks).

4) Background jobs (Celery)
- Tasks: scan base path, parse files, upsert into DB, enrich from Goodreads (optional/dry-run friendly).
- RabbitMQ broker; Celery worker (and beat optional for periodic scan).

5) Frontend UX
- List books with search/filter, edit fields (title, author, Goodreads URL, image URL).
- Merge multiple highlights into `MergedHighlight` without deleting originals.

6) Dockerization
- Images for web and worker (shared base image). Services: web, worker, rabbitmq, postgres.
- Mount host highlights directory read-only.

7) Testing
- Unit tests for `core` (parsing, aggregation, merge logic). Lightweight DB tests for models.

## Config & Constraints
- Do not modify KoReader JSON/Lua files; only read.
- Base path configurable via env (`HIGHLIGHTS_BASE_PATH`).
- Credentials/secrets via `.env`/env vars; no auth in app (LAN-only).
