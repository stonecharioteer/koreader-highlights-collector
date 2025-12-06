<p align="center">
  <img src="assets/logo.png" alt="KOReader Highlights Collector" height="72" />
</p>

# KOReader Highlights Collector (Web App)

Browse, search, and enrich your KOReader highlights from all your devices via a local Flask web application. The app scans KOReader metadata files, aggregates highlights with device labels, and lets you enhance book metadata using Open Library.

**Important**: This application does **not** sync highlights back to your devices. It's a read-only collector and viewer. Use [Syncthing](https://syncthing.net/) or similar tools to synchronize your KOReader metadata across devices.

![Landing](assets/banner.png)

## Prerequisites: Syncing Highlights with Syncthing

This application is designed to work with highlights that are already synchronized from your devices. Here's the recommended setup:

### 1. Centralize KOReader Metadata

On each KOReader device, ensure metadata is stored in a central location:

- Go to KOReader Settings → Document → Document metadata folder
- Set to a centralized path (e.g., `/mnt/us/koreader/docsettings` on Kindle)
- This ensures all book metadata and highlights are in one place per device

### 2. Sync with Syncthing

Install [Syncthing](https://syncthing.net/) on your devices and central server/laptop:

1. On each KOReader device, share the `docsettings` folder with your central server
2. On your central server, configure Syncthing to receive these folders
3. Organize synced folders by device, e.g.:
   ```
   ~/syncthing/koreader-highlights/
   ├── boox-palma/
   ├── kindle-paperwhite/
   └── kobo-libra/
   ```

### 3. Mount in Docker

Update your `docker-compose.yml` to mount your synced highlights:

```yaml
services:
  web:
    volumes:
      - ~/syncthing/koreader-highlights:/data/highlights:ro
  worker:
    volumes:
      - ~/syncthing/koreader-highlights:/data/highlights:ro
```

The `:ro` (read-only) flag ensures the application never modifies your source files.

## Quick Start (Docker Compose)

```bash
docker compose up --build
```

- App: http://localhost:48138
- RabbitMQ UI: http://localhost:15672 (guest/guest)
- Postgres: localhost:5432

The default compose mounts `./sample-highlights` as an example. Replace this with your actual Syncthing folder as described above.

## Configure

1) Open the app → Config

- **Add Source Folders**: Point to your highlights directories. You can add:
  - Individual device folders: `/data/highlights/boox-palma`, `/data/highlights/kindle-paperwhite`
  - Or the parent folder: `/data/highlights` (will scan all subdirectories)
- **Device Labels** (optional): If not set, the folder name is used (e.g., `/data/highlights/boox-palma` → `boox-palma`)
- **Open Library Identity**: Set App Name and Contact Email for API requests (sent in User-Agent)

2) Scan

- Click **Scan All** to trigger a background import
- The Celery worker reads KOReader metadata files (`metadata.*.lua`)
- Highlights are aggregated per book and tagged with device labels
- The app never modifies your source files (read-only access)

## UI Overview

- **Books List**: Search and browse imported books with cover thumbnails, highlight counts, and Open Library links
- **Book Detail**:
  - View all highlights with page/chapter/date, device tags, and type badges
  - Filter by device or highlight type
  - Click any highlight to view in a beautiful shareable quote modal
  - Download quotes as PNG images with adaptive layouts
  - Edit metadata inline or search Open Library
  - Upload covers or fetch from URLs (stored in database)
- **Config**: Manage source folders, configure Open Library identity, migrate images to database

## Design Philosophy

- **Read-only ingestion**: Source KOReader files are never modified; database is the system of record
- **No syncing**: This app collects and displays highlights; it doesn't sync back to devices (use Syncthing for that)
- **Device tracking**: Configured labels per folder track which device highlights came from
- **Aggregation, not merging**: Highlights from all devices are collected and displayed together; originals are preserved

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
