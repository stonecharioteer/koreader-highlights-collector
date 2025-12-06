# TODO

## Phase 1 — Core & Models
- [x] Extract parsing logic into `core/` package with clear APIs.
- [x] Replace dataclasses with Pydantic models (`ParsedFile`, `DocProps`, `ParserAnnotation`) and enum `HighlightKind`.
- [x] Design SQLAlchemy models: Book, Highlight, Note, Bookmark, MergedHighlight, MergedHighlightItem.
- [x] DB session via Flask‑SQLAlchemy; `DATABASE_URL` config.

## Phase 2 — Flask App
- [x] Create Flask app factory with blueprints: books, tasks, config.
- [x] Pages: books list, book detail with highlights, edit book form, merge UI.
- [x] Templates with Bootstrap.
- [x] Config page: manage source folders with device labels; set Open Library App Name + Contact Email.

## Phase 3 — Celery
- [x] Configure Celery (RabbitMQ) and integrate with Flask app context.
- [x] Implement tasks: scan (all paths), import file; read-only ingestion.
- [x] Device ID inference and folder‑derived title fallback.
- [x] Dedupe highlights per book and attach device tags.

## Phase 4 — Docker & Compose
- [x] Multi-stage Dockerfile: generate requirements from pyproject (pip-compile) and pip install.
- [x] docker-compose: web, worker, rabbitmq, postgres.
- [x] Mount highlights directory read-only and DB volume.
- [x] Web on port 48138.

## Phase 5 — Tests & Docs
- [x] Unit tests: parser, collector, Flask smoke.
- [x] Coverage with pytest‑cov (threshold 60%).
- [ ] Add DB import tests (SQLite) for idempotency and merge.
- [ ] Update README with app usage and compose instructions.
- [x] Update PLAN/ARCHITECTURE to reflect Open Library, device labels, dedupe, port.

## Nice-to-haves
- [ ] Alembic migrations; add indexes (Book.checksum, clean_title, raw_title).
- [ ] Celery Beat for periodic scans; job status feedback in UI.
- [ ] Enhanced search/filter (by author, device, date range).
- [ ] Idempotent upserts for highlights (hash on checksum/device_id/pos or datetime+text) to avoid duplicates on re-scan (beyond current per-book text/page rule).
- [ ] Display merged highlights on book page; add unmerge/delete.
- [ ] Admin: merge duplicate books (choose primary; reassign children).
- [ ] Config UX: validate paths exist/readable; show detected file counts.
- [ ] Open Library: cache and rate limit requests; show fetch errors.
- [ ] Pagination for large books lists; sorting options.
