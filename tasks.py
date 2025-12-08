from pathlib import Path
from typing import Optional
import hashlib
import re
from celery.utils.log import get_task_logger
from flask import current_app

from celery_app import make_celery
from app import create_app, db
from app.models import Book, Highlight, Bookmark, Note, SourcePath, HighlightDevice, Job, ExportJob, AppConfig
from core import LuaTableParser, iter_metadata_files, HighlightKind
import json
from datetime import datetime, timedelta


flask_app = create_app()
celery = make_celery(flask_app)
logger = get_task_logger(__name__)


def _scan_base_path_internal(base: Path, device_label: Optional[str] = None) -> int:
    if not base.exists():
        logger.warning("Base path does not exist: %s", base)
        return 0
    count = 0
    for path in iter_metadata_files(base):
        if device_label:
            device_id = device_label
        else:
            try:
                rel = path.relative_to(base)
                first = rel.parts[0] if rel.parts else None
            except Exception:
                first = None
            first_lower = (first or '').lower()
            device_id = base.name if first_lower in {"storage", "internal", "sdcard"} else (first or base.name or 'unknown')
        import_file(str(path), device_id=device_id)
        count += 1
    return count


@celery.task(name='tasks.scan_base_path')
def scan_base_path(base_path: Optional[str] = None):
    base = Path(base_path or current_app.config['HIGHLIGHTS_BASE_PATH'])
    count = _scan_base_path_internal(base)
    logger.info("Scanned %s files in %s", count, base)
    return count


@celery.task(name='tasks.scan_all_paths', bind=True)
def scan_all_paths(self):
    task_id = self.request.id

    # Create job record
    job = Job(
        job_id=task_id,
        job_type='scan',
        status='processing'
    )
    db.session.add(job)
    db.session.commit()

    try:
        # Track statistics
        books_before = Book.query.count()
        highlights_before = Highlight.query.count()

        total = 0
        paths = SourcePath.query.filter_by(enabled=True).order_by(SourcePath.path.asc()).all()
        if paths:
            for sp in paths:
                total += _scan_base_path_internal(Path(sp.path), device_label=sp.device_label if hasattr(sp, 'device_label') else None)
        else:
            logger.info("No source paths configured; skipping scan.")

        # Calculate new items
        books_after = Book.query.count()
        highlights_after = Highlight.query.count()
        new_books = books_after - books_before
        new_highlights = highlights_after - highlights_before

        logger.info("Scanned total %s files across configured paths", total)
        logger.info("Added %s new book(s) and %s new highlight(s)", new_books, new_highlights)

        # Update job record
        job.status = 'completed'
        job.result_summary = json.dumps({
            'files_scanned': total,
            'paths_count': len(paths) if paths else 0,
            'new_books': new_books,
            'new_highlights': new_highlights,
            'total_books': books_after,
            'total_highlights': highlights_after
        })
        job.completed_at = datetime.utcnow()
        db.session.commit()

        return total
    except Exception as e:
        logger.exception("Scan failed: %s", e)
        job.status = 'failed'
        job.error_message = str(e)
        job.completed_at = datetime.utcnow()
        db.session.commit()
        raise


@celery.task(name='tasks.import_file')
def import_file(path: str, device_id: str = 'unknown'):
    p = Path(path)
    try:
        parsed = LuaTableParser.parse_file(p)
    except Exception as e:
        logger.exception("Failed parsing %s: %s", p, e)
        return 0

    annotations = parsed.annotations or []
    doc_props = parsed.doc_props or None
    checksum = parsed.partial_md5_checksum

    # Upsert book
    # Derive normalized title key for fallback grouping
    parent_name = p.parent.name
    folder_title = parent_name[:-4] if parent_name.lower().endswith('.sdr') else parent_name
    folder_title = folder_title.replace('_', ' ').strip()
    title_candidate = (parsed.doc_props.title if (parsed.doc_props and parsed.doc_props.title) else folder_title) or None
    norm_title = re.sub(r"\s+", " ", (title_candidate or '')).strip().lower() or None

    book = None
    if checksum:
        book = Book.query.filter_by(checksum=checksum).first()
        if not book and norm_title:
            # attempt to find by normalized title across existing books
            from sqlalchemy import func
            book = Book.query.filter(func.lower(Book.clean_title) == norm_title).first() or \
                   Book.query.filter(func.lower(Book.raw_title) == norm_title).first()
    else:
        if norm_title:
            from sqlalchemy import func
            book = Book.query.filter(func.lower(Book.clean_title) == norm_title).first() or \
                   Book.query.filter(func.lower(Book.raw_title) == norm_title).first()

    if not book:
        # Build a stable key of max 64 chars when checksum missing
        if checksum:
            key = checksum
        else:
            base = norm_title or str(p)
            key = hashlib.sha256(base.encode('utf-8', errors='ignore')).hexdigest()  # 64 hex chars
        book = Book(checksum=key)
    if not getattr(book, 'raw_title', None):
        book.raw_title = title_candidate

    if doc_props:
        book.raw_authors = doc_props.authors or book.raw_authors
        book.identifiers = doc_props.identifiers or book.identifiers
        book.language = doc_props.language or book.language
        book.description = doc_props.description or book.description

    # Seed clean_title from candidate if empty
    if not getattr(book, 'clean_title', None):
        book.clean_title = title_candidate
    book.file_path = parsed.doc_path or book.file_path
    db.session.add(book)
    db.session.flush()

    imported = 0
    for ann in annotations:
        kind = ann.kind

        if kind == HighlightKind.bookmark and ann.text:
            # treat as Note if textual bookmark
            note = Note(
                book_id=book.id,
                text=ann.text or '',
                datetime=ann.datetime or '',
                device_id=device_id,
            )
            db.session.add(note)
            imported += 1
            continue

        if kind in {HighlightKind.highlight, HighlightKind.highlight_empty, HighlightKind.highlight_no_position}:
            # Deduplicate by content within a book (ignore exact kind and page number)
            # Page numbers can differ across devices/editions, so we dedupe by text only
            existing = Highlight.query.filter(
                Highlight.book_id == book.id,
                Highlight.text == (ann.text or ''),
                Highlight.kind.in_(['highlight', 'highlight_empty', 'highlight_no_position'])
            ).first()
            if existing:
                # attach device tag if missing
                if device_id and not any(d.device_id == device_id for d in existing.devices):
                    db.session.add(HighlightDevice(highlight_id=existing.id, device_id=device_id))
                # Optionally update missing fields (chapter/datetime/page_xpath/color)
                if not existing.chapter and ann.chapter:
                    existing.chapter = ann.chapter
                if not existing.datetime and ann.datetime:
                    existing.datetime = ann.datetime
                if not existing.page_xpath and ann.page:
                    existing.page_xpath = ann.page
                if not existing.color and ann.color:
                    existing.color = ann.color
                # Update page_number only if existing is 0 and new is non-zero
                # (prefer actual page numbers over missing ones)
                if existing.page_number == 0 and ann.pageno and ann.pageno > 0:
                    existing.page_number = ann.pageno
                db.session.add(existing)
            else:
                h = Highlight(
                    book_id=book.id,
                    text=ann.text or '',
                    chapter=ann.chapter or '',
                    page_number=ann.pageno or 0,
                    datetime=ann.datetime or '',
                    color=ann.color or '',
                    drawer=ann.drawer or '',
                    device_id=device_id,
                    page_xpath=ann.page or '',
                    kind=kind.value,
                )
                db.session.add(h)
                db.session.flush()
                if device_id:
                    db.session.add(HighlightDevice(highlight_id=h.id, device_id=device_id))
                imported += 1
        elif kind == HighlightKind.unknown:
            # ignore
            pass

    db.session.commit()
    logger.info("Imported %s annotations for %s", imported, book.raw_title or book.clean_title or book.id)
    return imported


@celery.task(name='tasks.export_highlights')
def export_highlights(job_id: str):
    """Render highlights export using Jinja template and create zip file.

    Args:
        job_id: UUID of the ExportJob to process
    """
    import json
    import zipfile
    import tempfile
    from datetime import datetime
    from jinja2 import Template
    from app.models import ExportJob, ExportTemplate, Book, Highlight

    job = ExportJob.query.filter_by(job_id=job_id).first()
    if not job:
        logger.error("Export job %s not found", job_id)
        return

    try:
        job.status = 'processing'
        db.session.commit()

        # Load data
        book = Book.query.get(job.book_id)
        template = ExportTemplate.query.get(job.template_id)
        highlight_ids = json.loads(job.highlight_ids)
        highlights = Highlight.query.filter(Highlight.id.in_(highlight_ids)).order_by(Highlight.page_number, Highlight.datetime).all()

        # Calculate read range
        dates = [h.datetime for h in highlights if h.datetime]
        read_start = min(dates).split(' ')[0] if dates else None
        read_end = max(dates).split(' ')[0] if dates else None

        # Prepare template context
        export_date = datetime.now().strftime('%Y-%m-%d')
        template_context = {
            'book': book,
            'highlights': highlights,
            'read_start': read_start,
            'read_end': read_end,
            'current_date': export_date,
            'current_timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'book_title': book.clean_title or book.raw_title or 'book',
            'book_authors': book.clean_authors or book.raw_authors or '',
            'export_date': export_date
        }

        # Render content template
        jinja_template = Template(template.template_content)
        rendered = jinja_template.render(**template_context)

        # Render filename templates
        def sanitize_filename(name: str) -> str:
            """Sanitize a filename by removing invalid characters."""
            # Remove invalid characters
            safe = re.sub(r'[^\w\s.-]', '', name)
            # Collapse whitespace and hyphens
            safe = re.sub(r'[-\s]+', '_', safe).strip('_')
            # Limit length
            return safe[:200]

        filename_template = Template(template.filename_template)
        rendered_filename = filename_template.render(**template_context)
        safe_filename = sanitize_filename(rendered_filename)

        cover_filename_template = Template(template.cover_filename_template)
        rendered_cover_filename = cover_filename_template.render(**template_context)
        safe_cover_filename = sanitize_filename(rendered_cover_filename)

        # Create zip file
        exports_dir = Path(current_app.config.get('EXPORT_DIR', '/tmp/exports'))
        exports_dir.mkdir(parents=True, exist_ok=True)

        zip_path = exports_dir / f"export_{job_id}.zip"
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            # Add rendered content
            zf.writestr(safe_filename, rendered)

            # Add book cover if available
            if book.image_data:
                ext = 'jpg' if book.image_content_type == 'image/jpeg' else 'png'
                zf.writestr(f'{safe_cover_filename}.{ext}', book.image_data)

        job.status = 'completed'
        job.file_path = str(zip_path)
        job.completed_at = datetime.utcnow()
        db.session.commit()

        logger.info("Completed export job %s: %s highlights from '%s'",
                   job_id, len(highlights), book.clean_title or book.raw_title)

    except Exception as e:
        logger.exception("Failed export job %s: %s", job_id, e)
        job.status = 'failed'
        job.error_message = str(e)
        db.session.commit()


@celery.task(name='tasks.cleanup_old_jobs')
def cleanup_old_jobs():
    """Delete old jobs and their associated files based on retention policy.

    Runs daily at midnight to clean up:
    - Job records older than retention_days
    - ExportJob records older than retention_days
    - Associated export zip files
    """
    # Get retention policy from config
    cfg = AppConfig.query.first()
    retention_days = cfg.job_retention_days if cfg else 30

    cutoff_date = datetime.utcnow() - timedelta(days=retention_days)

    # Clean up Job records (scan jobs)
    old_jobs = Job.query.filter(Job.created_at < cutoff_date).all()
    jobs_deleted = len(old_jobs)
    for job in old_jobs:
        db.session.delete(job)

    # Clean up ExportJob records and their files
    old_export_jobs = ExportJob.query.filter(ExportJob.created_at < cutoff_date).all()
    export_jobs_deleted = len(old_export_jobs)
    files_deleted = 0

    for job in old_export_jobs:
        # Delete the export file if it exists
        if job.file_path:
            try:
                file_path = Path(job.file_path)
                if file_path.exists():
                    file_path.unlink()
                    files_deleted += 1
            except Exception as e:
                logger.warning(f"Failed to delete export file {job.file_path}: {e}")

        db.session.delete(job)

    db.session.commit()

    logger.info(
        "Cleanup completed: deleted %d Job record(s), %d ExportJob record(s), and %d export file(s) older than %d days",
        jobs_deleted, export_jobs_deleted, files_deleted, retention_days
    )

    return {
        'jobs_deleted': jobs_deleted,
        'export_jobs_deleted': export_jobs_deleted,
        'files_deleted': files_deleted,
        'retention_days': retention_days
    }
