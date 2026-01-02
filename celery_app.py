import os
from celery import Celery


def make_celery(flask_app):
    celery = Celery(
        flask_app.import_name,
        broker=flask_app.config["CELERY_BROKER_URL"],
        backend=flask_app.config.get("CELERY_RESULT_BACKEND", "rpc://"),
        include=["tasks"],
    )
    celery.conf.update(task_ignore_result=True)

    # Configure Celery Beat schedule
    from celerybeat_schedule import get_beat_schedule

    celery.conf.beat_schedule = get_beat_schedule()
    celery.conf.timezone = "UTC"

    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with flask_app.app_context():
                return self.run(*args, **kwargs)

    celery.Task = ContextTask
    return celery
