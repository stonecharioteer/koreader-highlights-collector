<p align="center">
  <img src="assets/logo.png" alt="KOReader Highlights Collector" height="72" />
</p>

# KOReader Highlights Collector (Web App)

Manage KOReader highlights across devices via a local Flask app. The app scans KoReader metadata files, deduplicates highlights, tags them with device labels, and lets you clean up book metadata using Open Library.

![Landing](assets/banner.png)

## Quick Start (Docker Compose)

```bash
docker compose up --build
```

- App: http://localhost:48138
- RabbitMQ UI: http://localhost:15672 (guest/guest)
- Postgres: localhost:5432
- RustFS (image store): http://localhost:8080

The compose mounts `./sample-highlights` into the container at `/data/highlights` read‑only.

## Configure

1) Open the app → Config

- Add Source Folders: point to your highlights roots (parent or per-device). Optionally set a device label; if left blank, the last directory name is used (e.g., `/data/highlights/boox-palma` → `boox-palma`).
- Open Library Identity: set App Name and Contact Email; these are sent in the User-Agent for API requests.
- Image Store: set RustFS base URL (e.g., `http://rustfs:8080`) to store covers locally and serve them from your network.

2) Scan

- Click Scan to enqueue a background import. The worker reads KoReader metadata, dedupes highlights per book by content (text + page), and attaches device tags.

## UI Overview

- Books: list of imported books (folder‑derived title fallback). Edit a book inline.
- Book Detail:
  - Highlights: pretty quotes with page/chapter/date, device pills, and type badge (Highlight, Empty, No Pos).
  - Open Library: search by title/author, apply a selected result to set clean title/author/cover; if RustFS is configured, covers are stored locally. You can refresh later via the saved URL.
  - Merge: select multiple highlights and create a merged highlight without deleting originals.

## Design Notes

- Read‑only ingestion: source KoReader files are never modified.
- Device detection: uses configured device labels per folder; otherwise infers from the first subfolder.
- Dedupe: per book, by (text, page_number) for highlight variants; device tags are merged.

## Local Development

Using uv:

```bash
uv sync
FLASK_APP=app:create_app uv run flask run  # http://127.0.0.1:5000
uv run celery -A tasks.celery worker -l info
```

Tests + coverage:

```bash
uv run pytest
```

## Legacy CLI (optional)

The original CLI (`collect_highlights.py`) remains for one‑off JSON exports and experiments. The web app is the primary interface going forward.
