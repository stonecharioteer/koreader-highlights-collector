-- Add scan_schedule column to app_config table
ALTER TABLE app_config
ADD COLUMN IF NOT EXISTS scan_schedule VARCHAR(100) DEFAULT '*/15 * * * *';

-- Remove deprecated rustfs_url column
ALTER TABLE app_config
DROP COLUMN IF EXISTS rustfs_url;

-- Add comment
COMMENT ON COLUMN app_config.scan_schedule IS 'Cron expression for periodic highlight scanning (default: every 15 minutes)';
