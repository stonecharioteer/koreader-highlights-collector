from pathlib import Path
from flask import Blueprint, current_app, redirect, url_for, flash
from ..models import SourcePath
from celery_app import make_celery

bp = Blueprint("tasks", __name__)


@bp.route("/tasks/scan")
def trigger_scan():
    app = current_app._get_current_object()
    celery = make_celery(app)
    # Only enqueue if there are enabled source paths
    from .. import db  # ensure app context

    if SourcePath.query.filter_by(enabled=True).count() == 0:
        flash("No source folders configured. Add folders in Config first.", "warning")
        return redirect(url_for("books.index"))
    celery.send_task("tasks.scan_all_paths")
    flash("Scan started in background.", "info")
    return redirect(url_for("books.index"))
