import json
import uuid
from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    jsonify,
    send_file,
)
from .. import db
from ..models import ExportTemplate, ExportJob, Book, Highlight
from celery_app import make_celery
from flask import current_app

bp = Blueprint("exports", __name__)


@bp.route("/templates")
def templates():
    """List all export templates"""
    templates = ExportTemplate.query.order_by(
        ExportTemplate.is_default.desc(), ExportTemplate.name
    ).all()
    return render_template("exports/templates.html", templates=templates)


@bp.route("/templates/new", methods=["GET", "POST"])
def template_new():
    """Create new export template"""
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        content = request.form.get("template_content", "").strip()
        filename_template = request.form.get("filename_template", "").strip()
        cover_filename_template = request.form.get(
            "cover_filename_template", ""
        ).strip()
        is_default = request.form.get("is_default") == "on"

        if (
            not name
            or not content
            or not filename_template
            or not cover_filename_template
        ):
            flash(
                "Template name, content, and filename templates are required.", "danger"
            )
            return render_template("exports/template_edit.html", template=None)

        # Unset other defaults if this is default
        if is_default:
            ExportTemplate.query.filter_by(is_default=True).update(
                {"is_default": False}
            )

        template = ExportTemplate(
            name=name,
            template_content=content,
            filename_template=filename_template,
            cover_filename_template=cover_filename_template,
            is_default=is_default,
        )
        db.session.add(template)
        db.session.commit()
        flash(f'Template "{name}" created successfully.', "success")
        return redirect(url_for("exports.templates"))

    return render_template("exports/template_edit.html", template=None)


@bp.route("/templates/<int:template_id>/edit", methods=["GET", "POST"])
def template_edit(template_id):
    """Edit existing export template"""
    template = ExportTemplate.query.get_or_404(template_id)

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        content = request.form.get("template_content", "").strip()
        filename_template = request.form.get("filename_template", "").strip()
        cover_filename_template = request.form.get(
            "cover_filename_template", ""
        ).strip()
        is_default = request.form.get("is_default") == "on"

        if (
            not name
            or not content
            or not filename_template
            or not cover_filename_template
        ):
            flash(
                "Template name, content, and filename templates are required.", "danger"
            )
            return render_template("exports/template_edit.html", template=template)

        # Unset other defaults if this is default
        if is_default and not template.is_default:
            ExportTemplate.query.filter_by(is_default=True).update(
                {"is_default": False}
            )

        template.name = name
        template.template_content = content
        template.filename_template = filename_template
        template.cover_filename_template = cover_filename_template
        template.is_default = is_default
        db.session.commit()
        flash(f'Template "{name}" updated successfully.', "success")
        return redirect(url_for("exports.templates"))

    return render_template("exports/template_edit.html", template=template)


@bp.route("/templates/<int:template_id>/delete", methods=["POST"])
def template_delete(template_id):
    """Delete export template"""
    template = ExportTemplate.query.get_or_404(template_id)
    name = template.name
    db.session.delete(template)
    db.session.commit()
    flash(f'Template "{name}" deleted.', "info")
    return redirect(url_for("exports.templates"))


@bp.route("/books/<int:book_id>/export", methods=["POST"])
def export_create(book_id):
    """Create export job for selected highlights"""
    book = Book.query.get_or_404(book_id)
    highlight_ids = request.form.getlist("highlight_ids[]")
    template_id = request.form.get("template_id", type=int)

    if not highlight_ids:
        flash("Please select at least one highlight to export.", "warning")
        return redirect(url_for("books.detail", book_id=book_id))

    if not template_id:
        # Use default template
        template = ExportTemplate.query.filter_by(is_default=True).first()
        if not template:
            flash("No export template configured. Please create one first.", "danger")
            return redirect(url_for("exports.templates"))
        template_id = template.id

    # Create job
    job_id = str(uuid.uuid4())
    job = ExportJob(
        job_id=job_id,
        book_id=book_id,
        template_id=template_id,
        highlight_ids=json.dumps([int(h) for h in highlight_ids]),
        status="pending",
    )
    db.session.add(job)
    db.session.commit()

    # Queue task
    app = current_app._get_current_object()
    celery = make_celery(app)
    celery.send_task("tasks.export_highlights", args=[job_id])

    # Redirect to unified jobs page
    flash(
        f"Export job created successfully. Check the Jobs page for status.", "success"
    )
    return redirect(url_for("jobs.index"))


@bp.route("/download/<job_id>")
def download(job_id):
    """Download completed export zip file"""
    job = ExportJob.query.filter_by(job_id=job_id).first_or_404()

    if job.status != "completed":
        flash("Export is not ready yet.", "warning")
        return redirect(url_for("exports.job_status", job_id=job_id))

    if not job.file_path:
        flash("Export file not found.", "danger")
        return redirect(url_for("exports.job_status", job_id=job_id))

    from pathlib import Path

    zip_path = Path(job.file_path)
    if not zip_path.exists():
        flash("Export file no longer exists.", "danger")
        return redirect(url_for("exports.job_status", job_id=job_id))

    return send_file(
        zip_path,
        as_attachment=True,
        download_name=f"highlights_export_{job.book.clean_title or job.book.raw_title}_{job_id[:8]}.zip",
    )


@bp.route("/jobs/<job_id>/delete", methods=["POST"])
def job_delete(job_id):
    """Delete a single export job and its file"""
    job = ExportJob.query.filter_by(job_id=job_id).first_or_404()

    # Delete the file if it exists
    if job.file_path:
        from pathlib import Path

        zip_path = Path(job.file_path)
        if zip_path.exists():
            try:
                zip_path.unlink()
            except Exception as e:
                flash(f"Failed to delete export file: {e}", "warning")

    # Delete the job record
    book_title = job.book.clean_title or job.book.raw_title
    db.session.delete(job)
    db.session.commit()

    flash(f'Export job for "{book_title}" deleted.', "info")
    return redirect(url_for("jobs.index"))
