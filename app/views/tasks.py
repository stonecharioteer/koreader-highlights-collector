from pathlib import Path
from flask import Blueprint, current_app, redirect, url_for
from celery_app import make_celery

bp = Blueprint('tasks', __name__)


@bp.route('/tasks/scan')
def trigger_scan():
    app = current_app._get_current_object()
    celery = make_celery(app)
    celery.send_task('tasks.scan_all_paths')
    return redirect(url_for('books.index'))
