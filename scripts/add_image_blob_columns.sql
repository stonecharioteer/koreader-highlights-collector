-- Migration: Add image_data and image_content_type columns to books table
-- Run with: psql -h localhost -U highlights -d highlights -f scripts/add_image_blob_columns.sql

ALTER TABLE books
ADD COLUMN IF NOT EXISTS image_data BYTEA,
ADD COLUMN IF NOT EXISTS image_content_type VARCHAR(100);

COMMENT ON COLUMN books.image_url IS 'Deprecated: use image_data instead. Keep for backward compatibility during migration.';
COMMENT ON COLUMN books.image_data IS 'Image stored as binary blob';
COMMENT ON COLUMN books.image_content_type IS 'MIME type of the image (e.g., image/jpeg, image/png)';
