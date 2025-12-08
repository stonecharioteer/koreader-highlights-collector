"""
Dynamic Celery Beat schedule configuration.

This module provides the beat_schedule for Celery Beat based on the database configuration.
The schedule is loaded from the AppConfig.scan_schedule field which uses cron syntax.
"""
from celery.schedules import crontab
from croniter import croniter


def get_beat_schedule():
    """
    Get the Celery Beat schedule from database configuration.

    Returns:
        dict: Celery Beat schedule dictionary
    """
    from app import create_app, db
    from app.models import AppConfig

    flask_app = create_app()

    with flask_app.app_context():
        config = AppConfig.query.first()
        cron_expression = config.scan_schedule if config and config.scan_schedule else '*/15 * * * *'

        # Validate cron expression
        try:
            croniter(cron_expression)
        except (ValueError, KeyError):
            # Fallback to default if invalid
            cron_expression = '*/15 * * * *'

        # Parse cron expression (minute hour day month day_of_week)
        parts = cron_expression.split()
        if len(parts) != 5:
            # Fallback to default if invalid format
            parts = ['*/15', '*', '*', '*', '*']

        return {
            'periodic-highlight-scan': {
                'task': 'tasks.scan_all_paths',
                'schedule': crontab(
                    minute=parts[0],
                    hour=parts[1],
                    day_of_month=parts[2],
                    month_of_year=parts[3],
                    day_of_week=parts[4]
                ),
                'options': {
                    'expires': 600  # Task expires after 10 minutes if not executed
                }
            },
            'daily-job-cleanup': {
                'task': 'tasks.cleanup_old_jobs',
                'schedule': crontab(minute='0', hour='0'),  # Run daily at midnight
                'options': {
                    'expires': 3600  # Task expires after 1 hour if not executed
                }
            }
        }


# This is loaded when Celery Beat starts
beat_schedule = get_beat_schedule()
