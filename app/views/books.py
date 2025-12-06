from flask import Blueprint, render_template, request, redirect, url_for, current_app, flash
from .. import db
from ..models import Book, Highlight, MergedHighlight, MergedHighlightItem, AppConfig, HighlightDevice
from ..services.openlibrary import fetch_from_url as fetch_ol, search as ol_search
from ..services.imagestore import store_image_from_url, store_image_from_bytes

bp = Blueprint('books', __name__)


@bp.route('/books')
def index():
    q = request.args.get('q', '').strip()
    query = Book.query
    if q:
        like = f"%{q}%"
        query = query.filter((Book.clean_title.ilike(like)) | (Book.raw_title.ilike(like)))
    books = query.order_by(Book.clean_title.asc().nullslast(), Book.raw_title.asc()).limit(200).all()
    # Compute highlight counts per book
    from sqlalchemy import func
    ids = [b.id for b in books]
    counts = {}
    total_highlights = 0
    if ids:
        rows = (
            db.session.query(Highlight.book_id, func.count(Highlight.id))
            .filter(Highlight.book_id.in_(ids))
            .filter(Highlight.kind.in_(['highlight','highlight_empty','highlight_no_position']))
            .group_by(Highlight.book_id)
            .all()
        )
        counts = {bid: cnt for bid, cnt in rows}
        total_highlights = sum(counts.values())
    return render_template('books/list.html', books=books, q=q, counts=counts, total_books=len(books), total_highlights=total_highlights)


@bp.route('/')
def landing():
    return render_template('landing.html')


@bp.route('/books/<int:book_id>')
def book_detail(book_id: int):
    book = Book.query.get_or_404(book_id)
    from sqlalchemy import or_, and_

    # Filters
    kind_filter = request.args.get('type', 'highlight').strip() or 'highlight'
    device_filter = request.args.get('device', '').strip()

    # Build query
    q = Highlight.query.filter(Highlight.book_id == book.id)
    allowed_kinds = ['highlight', 'highlight_empty', 'highlight_no_position']
    if kind_filter == 'all':
        q = q.filter(Highlight.kind.in_(allowed_kinds))
    else:
        if kind_filter not in allowed_kinds:
            kind_filter = 'highlight'
        q = q.filter(Highlight.kind == kind_filter)

    if device_filter:
        q = (q.outerjoin(HighlightDevice, HighlightDevice.highlight_id == Highlight.id)
               .filter(or_(Highlight.device_id == device_filter,
                           HighlightDevice.device_id == device_filter)))

    highlights = q.order_by(Highlight.page_number.asc()).all()

    # Compute device list for filters
    device_rows = (
        db.session.query(Highlight.device_id)
        .filter(Highlight.book_id == book.id, Highlight.device_id.isnot(None), Highlight.device_id != '')
        .distinct()
        .all()
    )
    devices_from_highlights = {d for (d,) in device_rows if d}
    device_rel_rows = (
        db.session.query(HighlightDevice.device_id)
        .join(Highlight, Highlight.id == HighlightDevice.highlight_id)
        .filter(Highlight.book_id == book.id)
        .distinct()
        .all()
    )
    devices = sorted(devices_from_highlights.union({d for (d,) in device_rel_rows if d}))

    # Compute read date range from highlight datetimes (use date part if available)
    dates = []
    for h in highlights:
        if h.datetime:
            d = h.datetime.split(' ')[0]
            dates.append(d)
    read_start = min(dates) if dates else None
    read_end = max(dates) if dates else None
    return render_template(
        'books/detail.html',
        book=book,
        highlights=highlights,
        highlight_count=len(highlights),
        read_start=read_start,
        read_end=read_end,
        devices=devices,
        selected_device=device_filter,
        selected_type=kind_filter,
        ol_results=None
    )


@bp.route('/books/<int:book_id>/edit', methods=['GET', 'POST'])
def book_edit(book_id: int):
    book = Book.query.get_or_404(book_id)
    if request.method == 'POST':
        new_clean_title = request.form.get('clean_title') or None
        new_clean_authors = request.form.get('clean_authors') or None
        new_goodreads_url = request.form.get('goodreads_url') or None
        new_image_url = request.form.get('image_url') or None

        # Detect Goodreads URL update and fetch metadata
        url_changed = (new_goodreads_url or None) != (book.goodreads_url or None)
        if url_changed and new_goodreads_url:
            cfg = AppConfig.query.first()
            app_name = cfg.ol_app_name if cfg else None
            email = cfg.ol_contact_email if cfg else None
            try:
                meta = fetch_ol(new_goodreads_url, app_name=app_name, email=email)
                if meta.get('title'):
                    new_clean_title = meta['title']
                if meta.get('authors'):
                    new_clean_authors = meta['authors']
                if meta.get('image'):
                    # Store image to RustFS if configured
                    stored = store_image_from_url(meta['image'], rustfs_base=(cfg.rustfs_url if cfg else None))
                    new_image_url = stored or meta['image']
                # persist normalized openlibrary URL if provided
                if meta.get('url'):
                    new_goodreads_url = meta['url']
            except Exception:
                pass

        book.clean_title = new_clean_title
        book.clean_authors = new_clean_authors
        book.goodreads_url = new_goodreads_url
        book.image_url = new_image_url
        db.session.add(book)
        db.session.commit()
        flash('Book metadata updated.', 'success')
        return redirect(url_for('books.book_detail', book_id=book.id))
    return render_template('books/edit.html', book=book)


@bp.route('/books/<int:book_id>/merge', methods=['POST'])
def book_merge(book_id: int):
    book = Book.query.get_or_404(book_id)
    ids = request.form.getlist('highlight_id')
    text = request.form.get('merged_text') or ''
    notes = request.form.get('merged_notes') or None
    if not ids or not text.strip():
        return redirect(url_for('books.book_detail', book_id=book.id))
    merged = MergedHighlight(book_id=book.id, text=text.strip(), notes=notes)
    db.session.add(merged)
    db.session.flush()
    for sid in ids:
        try:
            hid = int(sid)
        except ValueError:
            continue
        db.session.add(MergedHighlightItem(merged_id=merged.id, highlight_id=hid))
    db.session.commit()
    return redirect(url_for('books.book_detail', book_id=book.id))


@bp.post('/books/<int:book_id>/ol-search')
def book_ol_search(book_id: int):
    book = Book.query.get_or_404(book_id)
    q = (request.form.get('q') or book.clean_title or book.raw_title or '').strip()
    results = []
    if q:
        cfg = AppConfig.query.first()
        app_name = cfg.ol_app_name if cfg else None
        email = cfg.ol_contact_email if cfg else None
        try:
            results = ol_search(q, app_name=app_name, email=email, limit=8)
        except Exception:
            results = []
    # Quiet search feedback
    highlights = Highlight.query.filter_by(book_id=book.id, kind='highlight').order_by(Highlight.page_number.asc()).all()
    return render_template('books/detail.html', book=book, highlights=highlights, ol_results=results, q=q)


@bp.post('/books/<int:book_id>/ol-apply')
def book_ol_apply(book_id: int):
    book = Book.query.get_or_404(book_id)
    url = request.form.get('url') or ''
    cfg = AppConfig.query.first()
    app_name = cfg.ol_app_name if cfg else None
    email = cfg.ol_contact_email if cfg else None
    try:
        meta = fetch_ol(url, app_name=app_name, email=email)
        if meta.get('title'):
            book.clean_title = meta['title']
        if meta.get('authors'):
            book.clean_authors = meta['authors']
        if meta.get('image'):
            stored = store_image_from_url(meta['image'], rustfs_base=(cfg.rustfs_url if cfg else None))
            book.image_url = stored or meta['image']
        if meta.get('url'):
            book.goodreads_url = meta['url']
        db.session.add(book)
        db.session.commit()
    except Exception:
        flash('Failed to apply Open Library metadata.', 'danger')
    return redirect(url_for('books.book_detail', book_id=book.id))


@bp.post('/books/<int:book_id>/refresh')
def book_refresh(book_id: int):
    book = Book.query.get_or_404(book_id)
    if not book.goodreads_url:
        return redirect(url_for('books.book_detail', book_id=book.id))
    cfg = AppConfig.query.first()
    app_name = cfg.ol_app_name if cfg else None
    email = cfg.ol_contact_email if cfg else None
    try:
        meta = fetch_ol(book.goodreads_url, app_name=app_name, email=email)
        if meta.get('title'):
            book.clean_title = meta['title']
        if meta.get('authors'):
            book.clean_authors = meta['authors']
        if meta.get('image'):
            stored = store_image_from_url(meta['image'], rustfs_base=(cfg.rustfs_url if cfg else None))
            book.image_url = stored or meta['image']
        db.session.add(book)
        db.session.commit()
    except Exception:
        flash('Failed to refresh Open Library metadata.', 'danger')
    return redirect(url_for('books.book_detail', book_id=book.id))


@bp.post('/books/<int:book_id>/update')
def book_update_inline(book_id: int):
    book = Book.query.get_or_404(book_id)
    book.clean_title = (request.form.get('clean_title') or '').strip() or None
    book.clean_authors = (request.form.get('clean_authors') or '').strip() or None
    book.image_url = (request.form.get('image_url') or '').strip() or None
    db.session.add(book)
    db.session.commit()
    flash('Saved edits.', 'success')
    return redirect(url_for('books.book_detail', book_id=book.id))


@bp.get('/books/<int:book_id>/cover')
def cover_image(book_id: int):
    """Serve or redirect to a book's cover image.
    If RustFS is configured and the current image_url is external, attempt to store
    it in RustFS, update the DB, and redirect to the stored URL.
    """
    book = Book.query.get_or_404(book_id)
    if not book.image_url:
        # No image; return 404 to let browser hide image
        return ('', 404)
    cfg = AppConfig.query.first()
    rustfs = cfg.rustfs_url if cfg else None
    if rustfs and not book.image_url.startswith(rustfs.rstrip('/')):
        stored = store_image_from_url(book.image_url, rustfs_base=rustfs)
        if stored:
            book.image_url = stored
            db.session.add(book)
            db.session.commit()
            return redirect(book.image_url)
    return redirect(book.image_url)


@bp.post('/books/<int:book_id>/image-upload')
def book_image_upload(book_id: int):
    book = Book.query.get_or_404(book_id)
    f = request.files.get('file')
    if not f or not f.filename:
        return redirect(url_for('books.book_detail', book_id=book.id))
    content = f.read()
    content_type = f.mimetype or 'image/jpeg'
    cfg = AppConfig.query.first()
    stored = store_image_from_bytes(content, content_type, rustfs_base=(cfg.rustfs_url if cfg else None), filename=f.filename)
    if stored:
        book.image_url = stored
        db.session.add(book)
        db.session.commit()
        flash('Cover image uploaded.', 'success')
    else:
        flash('Failed to upload cover image.', 'danger')
    return redirect(url_for('books.book_detail', book_id=book.id))


@bp.post('/books/<int:book_id>/image-fetch')
def book_image_fetch(book_id: int):
    book = Book.query.get_or_404(book_id)
    remote = (request.form.get('image_fetch_url') or '').strip()
    if not remote:
        return redirect(url_for('books.book_detail', book_id=book.id))
    cfg = AppConfig.query.first()
    stored = store_image_from_url(remote, rustfs_base=(cfg.rustfs_url if cfg else None))
    if stored or remote:
        book.image_url = stored or remote
        db.session.add(book)
        db.session.commit()
        flash('Cover image updated from URL.', 'success')
    else:
        flash('Failed to fetch image from URL.', 'danger')
    return redirect(url_for('books.book_detail', book_id=book.id))
