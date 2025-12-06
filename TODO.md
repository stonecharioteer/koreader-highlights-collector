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
- [x] Config page: manage source folders; configure Goodreads API key.

## Phase 3 — Celery
- [x] Configure Celery (RabbitMQ) and integrate with Flask app context.
- [x] Implement tasks: scan (all paths), import file; read-only ingestion.
- [x] Device ID inference and folder‑derived title fallback.

## Phase 4 — Docker & Compose
- [x] Multi-stage Dockerfile (uv builder → slim runtime).
- [x] docker-compose: web, worker, rabbitmq, postgres.
- [x] Mount highlights directory read-only and DB volume.

## Phase 5 — Tests & Docs
- [x] Unit tests: parser, collector, Flask smoke.
- [x] Coverage with pytest‑cov (threshold 60%).
- [ ] Add DB import tests (SQLite) for idempotency and merge.
- [ ] Update README with app usage and compose instructions.

## Nice-to-haves
- [ ] Alembic migrations; add indexes (Book.checksum, clean_title, raw_title).
- [ ] Celery Beat for periodic scans; job status feedback in UI.
- [ ] Enhanced search/filter (by author, device, date range).
- [ ] Idempotent upserts for highlights (hash on checksum/device_id/pos or datetime+text) to avoid duplicates on re-scan.
- [ ] Display merged highlights on book page; add unmerge/delete.
- [ ] Admin: merge duplicate books (choose primary; reassign children).
- [ ] Config UX: validate paths exist/readable; show detected file counts.
- [ ] Goodreads: rate limit + caching; error banner on edit when fetch fails.
- [ ] Pagination for large books lists; sorting options.
