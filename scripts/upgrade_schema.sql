-- Safe, idempotent schema upgrades for new app features

-- AppConfig new columns
ALTER TABLE IF EXISTS app_config
  ADD COLUMN IF NOT EXISTS ol_app_name VARCHAR(100),
  ADD COLUMN IF NOT EXISTS ol_contact_email VARCHAR(200),
  ADD COLUMN IF NOT EXISTS rustfs_url VARCHAR(300);

-- SourcePath device label
ALTER TABLE IF EXISTS source_paths
  ADD COLUMN IF NOT EXISTS device_label VARCHAR(200);

-- HighlightDevice table
CREATE TABLE IF NOT EXISTS highlight_devices (
  id SERIAL PRIMARY KEY,
  highlight_id INTEGER NOT NULL REFERENCES highlights(id) ON DELETE CASCADE,
  device_id VARCHAR NOT NULL,
  CONSTRAINT uq_highlight_device UNIQUE (highlight_id, device_id)
);

-- Add kind to highlights if missing
ALTER TABLE IF EXISTS highlights
  ADD COLUMN IF NOT EXISTS kind VARCHAR DEFAULT 'highlight';

-- Helpful indexes
CREATE INDEX IF NOT EXISTS idx_books_checksum ON books (checksum);
CREATE INDEX IF NOT EXISTS idx_highlights_book ON highlights (book_id);

