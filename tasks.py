from pathlib import Path
from typing import Optional
import hashlib
import re
from celery.utils.log import get_task_logger
from flask import current_app

from celery_app import make_celery
from app import create_app, db
from app.models import Book, Highlight, Bookmark, Note, SourcePath, HighlightDevice
from core import LuaTableParser, iter_metadata_files, HighlightKind


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


@celery.task(name='tasks.scan_all_paths')
def scan_all_paths():
    total = 0
    paths = SourcePath.query.filter_by(enabled=True).order_by(SourcePath.path.asc()).all()
    if not paths:
        # Fallback to single configured path
        base = Path(current_app.config['HIGHLIGHTS_BASE_PATH'])
        total += _scan_base_path_internal(base)
    else:
        for sp in paths:
            total += _scan_base_path_internal(Path(sp.path), device_label=sp.device_label if hasattr(sp, 'device_label') else None)
    logger.info("Scanned total %s files across configured paths", total)
    return total


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
            # Deduplicate by content within a book (ignore exact kind)
            existing = Highlight.query.filter(
                Highlight.book_id == book.id,
                Highlight.text == (ann.text or ''),
                Highlight.page_number == (ann.pageno or 0),
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
