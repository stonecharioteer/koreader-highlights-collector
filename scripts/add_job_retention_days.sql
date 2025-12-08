-- Add job_retention_days column to app_config table
ALTER TABLE app_config
ADD COLUMN IF NOT EXISTS job_retention_days INTEGER NOT NULL DEFAULT 30;

-- Update existing rows to have the default value
UPDATE app_config
SET job_retention_days = 30
WHERE job_retention_days IS NULL;

COMMENT ON COLUMN app_config.job_retention_days IS 'Number of days to retain job records. Jobs older than this will be automatically deleted (default: 30)';
