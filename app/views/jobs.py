from flask import Blueprint, render_template, jsonify, redirect, url_for, flash
from pathlib import Path
from .. import db
from ..models import Job, ExportJob
from sqlalchemy import or_

bp = Blueprint("jobs", __name__)


@bp.route("/jobs")
def index():
    """List all jobs (scans and exports) in one view"""
    # Get all Job records
    jobs = Job.query.order_by(Job.created_at.desc()).limit(100).all()

    # Get all ExportJob records
    export_jobs = ExportJob.query.order_by(ExportJob.created_at.desc()).limit(100).all()

    # Combine and sort by creation time
    all_jobs = []

    for job in jobs:
        all_jobs.append(
            {
                "id": job.job_id,
                "type": job.job_type,
                "status": job.status,
                "created_at": job.created_at,
                "completed_at": job.completed_at,
                "error_message": job.error_message,
                "result_summary": job.result_summary,
                "is_export": False,
            }
        )

    for export_job in export_jobs:
        all_jobs.append(
            {
                "id": export_job.job_id,
                "type": "export",
                "status": export_job.status,
                "created_at": export_job.created_at,
                "completed_at": export_job.completed_at,
                "error_message": export_job.error_message,
                "book_title": export_job.book.clean_title or export_job.book.raw_title,
                "file_path": export_job.file_path,
                "is_export": True,
            }
        )

    # Sort by creation time
    all_jobs.sort(key=lambda x: x["created_at"], reverse=True)

    return render_template("jobs/index.html", jobs=all_jobs[:100])


@bp.route("/jobs/<job_id>/status.json")
def job_status_json(job_id):
    """Get job status as JSON for polling"""
    # Check Job table first
    job = Job.query.filter_by(job_id=job_id).first()
    if job:
        return jsonify(
            {
                "type": job.job_type,
                "status": job.status,
                "error_message": job.error_message,
                "result_summary": job.result_summary,
                "completed_at": job.completed_at.isoformat()
                if job.completed_at
                else None,
            }
        )

    # Check ExportJob table
    export_job = ExportJob.query.filter_by(job_id=job_id).first()
    if export_job:
        from flask import url_for

        return jsonify(
            {
                "type": "export",
                "status": export_job.status,
                "error_message": export_job.error_message,
                "completed_at": export_job.completed_at.isoformat()
                if export_job.completed_at
                else None,
                "download_url": url_for("exports.download", job_id=job_id)
                if export_job.status == "completed"
                else None,
            }
        )

    return jsonify({"error": "Job not found"}), 404


@bp.route("/jobs/clear-completed", methods=["POST"])
def clear_completed():
    """Delete all completed jobs (both scan and export jobs)"""
    # Delete completed Job records (scan jobs)
    completed_jobs = Job.query.filter_by(status="completed").all()
    scan_jobs_deleted = len(completed_jobs)
    for job in completed_jobs:
        db.session.delete(job)

    # Delete completed ExportJob records and their files
    completed_export_jobs = ExportJob.query.filter_by(status="completed").all()
    export_jobs_deleted = len(completed_export_jobs)
    files_deleted = 0

    for job in completed_export_jobs:
        # Delete the export file if it exists
        if job.file_path:
            try:
                file_path = Path(job.file_path)
                if file_path.exists():
                    file_path.unlink()
                    files_deleted += 1
            except Exception:
                pass

        db.session.delete(job)

    db.session.commit()

    flash(
        f"Cleared {scan_jobs_deleted} scan job(s) and {export_jobs_deleted} export job(s)",
        "success",
    )
    return redirect(url_for("jobs.index"))
