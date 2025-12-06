# Migration Plan: CLI → Web App

## Goals
- Local Flask web app to manage highlights metadata.
- Background ingestion via Celery with RabbitMQ; persist cleaned data in DB.
- Simple Bootstrap UI to list books, edit metadata, search Open Library and apply title/author/cover, and merge highlights.
- Never modify source KoReader files; read-only import into DB.
- Extract reusable parsing/collection code into a testable core library.

## Phases
1) Core library extraction
- Move parsing and collecting logic into `core/` package with pure functions and dataclasses.
- Keep CLI behavior available via thin wrappers (optional).

2) Data model & persistence
- SQLAlchemy models: `Book`, `Highlight`, `Note`, `Bookmark`, `MergedHighlight`, `MergedHighlightItem`, `SourcePath`, `HighlightDevice`, `AppConfig`.
- Store both raw and cleaned fields (e.g., `raw_title`, `clean_title`). Track device tags per highlight.
- Postgres via Docker Compose. Alembic for migrations (optional at start).

3) Web server (Flask)
- App factory, blueprints: `books`, `tasks`, `config`.
- Views: Book list, book detail (highlights with device pills + type), inline edit, Open Library search/select, merge tool.
- Jinja templates + Bootstrap (no JS frameworks).

4) Background jobs (Celery)
- Tasks: `scan_all_paths`, `import_file`; dedupe highlights by content per book; attach device tags.
- RabbitMQ broker; Celery worker (and beat optional for periodic scan).

5) Frontend UX
- List books with search/filter, edit fields (title, author, cover URL), Open Library search/apply, refresh saved URL.
- Merge multiple highlights into `MergedHighlight` without deleting originals.
- Config page to add source folders (with device label) and set Open Library app name/contact (User-Agent).

6) Dockerization
- Images for web and worker (shared base image). Services: web, worker, rabbitmq, postgres.
- Generate requirements.txt from `pyproject.toml` during build (pip-compile), then `pip install`.
- Expose port 48138 for the web app; mount host highlights directory read-only.

7) Testing
- Unit tests for `core` (parsing, aggregation, merge logic). Lightweight DB tests for models.
- pytest + pytest-cov with configured coverage threshold.

## Config & Constraints
- Do not modify KoReader JSON/Lua files; only read.
- Base path configurable via env (`HIGHLIGHTS_BASE_PATH`); additional folders managed in-app.
- Open Library requests identify with configurable App Name + Contact Email.
- No auth in app (LAN-only).
