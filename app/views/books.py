from flask import Blueprint, render_template, request, redirect, url_for, current_app, flash, Response, send_file
from .. import db
from ..models import Book, Highlight, MergedHighlight, MergedHighlightItem, AppConfig, HighlightDevice
from ..services.openlibrary import fetch_from_url as fetch_ol, search as ol_search
from ..services.imagestore import fetch_image_from_url
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont

bp = Blueprint('books', __name__)


def save_image_to_book(book: Book, image_data: bytes, content_type: str) -> bool:
    """Save image data to book model in database.

    Returns True on success, False on failure.
    """
    try:
        book.image_data = image_data
        book.image_content_type = content_type
        # Keep image_url as None or empty to indicate using database blob
        book.image_url = None
        return True
    except Exception as e:
        current_app.logger.error(f'Failed to save image data for book {book.id}: {e}')
        return False


def check_ol_config():
    """Check if Open Library credentials are configured.

    Returns tuple of (app_name, email) if configured, or (None, None) if not.
    Flashes an error message if not configured.
    """
    cfg = AppConfig.query.first()
    app_name = cfg.ol_app_name if cfg else None
    email = cfg.ol_contact_email if cfg else None

    if not app_name or not email:
        flash('Open Library credentials not configured. Please set App Name and Contact Email in Config.', 'danger')
        return None, None

    return app_name, email


@bp.route('/books')
def index():
    from sqlalchemy import func, case

    q = request.args.get('q', '').strip()
    sort_by = request.args.get('sort', 'title').strip()
    sort_order = request.args.get('order', 'asc').strip()

    # Base query with highlight counts
    query = db.session.query(
        Book,
        func.count(Highlight.id).label('highlight_count')
    ).outerjoin(
        Highlight,
        (Highlight.book_id == Book.id) &
        (Highlight.kind.in_(['highlight', 'highlight_empty', 'highlight_no_position']))
    ).group_by(Book.id)

    # Apply search filter
    if q:
        like = f"%{q}%"
        query = query.filter(
            (Book.clean_title.ilike(like)) |
            (Book.raw_title.ilike(like)) |
            (Book.clean_authors.ilike(like)) |
            (Book.raw_authors.ilike(like))
        )

    # Apply sorting
    if sort_by == 'title':
        sort_col = case(
            (Book.clean_title.isnot(None), Book.clean_title),
            else_=Book.raw_title
        )
    elif sort_by == 'author':
        sort_col = case(
            (Book.clean_authors.isnot(None), Book.clean_authors),
            else_=Book.raw_authors
        )
    elif sort_by == 'highlights':
        sort_col = func.count(Highlight.id)
    else:
        sort_col = Book.clean_title

    if sort_order == 'desc':
        query = query.order_by(sort_col.desc().nullslast())
    else:
        query = query.order_by(sort_col.asc().nullslast())

    # Execute query
    results = query.limit(200).all()
    books = [book for book, _ in results]
    counts = {book.id: count for book, count in results}
    total_highlights = sum(counts.values())

    return render_template(
        'books/list.html',
        books=books,
        q=q,
        counts=counts,
        total_books=len(books),
        total_highlights=total_highlights,
        sort_by=sort_by,
        sort_order=sort_order
    )


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
                    # Fetch and store image in database
                    result = fetch_image_from_url(meta['image'])
                    if result:
                        image_data, content_type = result
                        save_image_to_book(book, image_data, content_type)
                        new_image_url = None  # Use database blob
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

    # Check if Open Library is configured
    app_name, email = check_ol_config()
    if not app_name or not email:
        return redirect(url_for('books.book_detail', book_id=book.id))

    q = (request.form.get('q') or book.clean_title or book.raw_title or '').strip()
    results = []
    if q:
        try:
            results = ol_search(q, app_name=app_name, email=email, limit=8)
        except Exception:
            results = []
    # Quiet search feedback
    highlights = Highlight.query.filter_by(book_id=book.id, kind='highlight').order_by(Highlight.page_number.asc()).all()
    return render_template('books/detail.html', book=book, highlights=highlights, ol_results=results, q=q, expand_metadata=True)


@bp.post('/books/<int:book_id>/ol-apply')
def book_ol_apply(book_id: int):
    book = Book.query.get_or_404(book_id)

    # Check if Open Library is configured
    app_name, email = check_ol_config()
    if not app_name or not email:
        return redirect(url_for('books.book_detail', book_id=book.id))

    url = request.form.get('url') or ''

    try:
        meta = fetch_ol(url, app_name=app_name, email=email)
        if meta.get('title'):
            book.clean_title = meta['title']
        if meta.get('authors'):
            book.clean_authors = meta['authors']
        if meta.get('image'):
            # Fetch and store image in database
            result = fetch_image_from_url(meta['image'])
            if result:
                image_data, content_type = result
                if save_image_to_book(book, image_data, content_type):
                    flash('Cover image saved to database.', 'success')
                else:
                    flash('Failed to save image to database.', 'warning')
            else:
                flash('Failed to fetch image from URL.', 'warning')
        if meta.get('url'):
            book.goodreads_url = meta['url']
        db.session.add(book)
        db.session.commit()
    except Exception as e:
        flash(f'Failed to apply Open Library metadata: {str(e)}', 'danger')
    return redirect(url_for('books.book_detail', book_id=book.id))


@bp.post('/books/<int:book_id>/refresh')
def book_refresh(book_id: int):
    book = Book.query.get_or_404(book_id)
    if not book.goodreads_url:
        return redirect(url_for('books.book_detail', book_id=book.id))

    # Check if Open Library is configured
    app_name, email = check_ol_config()
    if not app_name or not email:
        return redirect(url_for('books.book_detail', book_id=book.id))

    try:
        meta = fetch_ol(book.goodreads_url, app_name=app_name, email=email)
        if meta.get('title'):
            book.clean_title = meta['title']
        if meta.get('authors'):
            book.clean_authors = meta['authors']
        if meta.get('image'):
            # Fetch and store image in database
            result = fetch_image_from_url(meta['image'])
            if result:
                image_data, content_type = result
                save_image_to_book(book, image_data, content_type)
        db.session.add(book)
        db.session.commit()
    except Exception as e:
        flash(f'Failed to refresh Open Library metadata: {str(e)}', 'danger')
    return redirect(url_for('books.book_detail', book_id=book.id))


@bp.post('/books/<int:book_id>/update')
def book_update_inline(book_id: int):
    book = Book.query.get_or_404(book_id)
    book.clean_title = (request.form.get('clean_title') or '').strip() or None
    book.clean_authors = (request.form.get('clean_authors') or '').strip() or None

    # Image URL field is now read-only in the UI; users should use "Fetch Cover by URL" button
    # If they somehow submit a URL, fetch and store it in database
    new_image_url = (request.form.get('image_url') or '').strip() or None
    if new_image_url and (new_image_url.startswith('http://') or new_image_url.startswith('https://')):
        result = fetch_image_from_url(new_image_url)
        if result:
            image_data, content_type = result
            if save_image_to_book(book, image_data, content_type):
                flash('Image fetched and saved to database.', 'success')
            else:
                flash('Failed to save image. Use the "Fetch Cover by URL" button instead.', 'warning')
        else:
            flash('Failed to fetch image from URL. Use the "Fetch Cover by URL" button instead.', 'warning')

    db.session.add(book)
    db.session.commit()
    flash('Saved edits.', 'success')
    return redirect(url_for('books.book_detail', book_id=book.id))


@bp.get('/books/<int:book_id>/cover')
def cover_image(book_id: int):
    """Serve book cover from database blob.
    Images are stored as binary data in the database for simplicity.
    """
    book = Book.query.get_or_404(book_id)
    if not book.image_data:
        # No image; return 404
        return ('', 404)

    # Serve the image data directly from database
    content_type = book.image_content_type or 'image/jpeg'
    return Response(book.image_data, mimetype=content_type)


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    # Try to load EB Garamond, fall back to default
    try:
        # Common path inside some images; otherwise Pillow default will be used
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf", size)
    except Exception:
        return ImageFont.load_default()


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int, max_lines: int = 12) -> str:
    words = text.split()
    lines = []
    line = ''
    for w in words:
        test = (line + ' ' + w).strip()
        if draw.textlength(test, font=font) <= max_width:
            line = test
        else:
            lines.append(line)
            line = w
            if len(lines) >= max_lines:
                break
    if line and len(lines) < max_lines:
        lines.append(line)
    if len(lines) >= max_lines:
        # indicate truncation
        lines[-1] = lines[-1].rstrip('.') + '…'
    return '\n'.join(lines)


@bp.get('/books/<int:book_id>/share/<int:highlight_id>.png')
def share_highlight(book_id: int, highlight_id: int):
    """Server-side render a shareable image (PNG) of a highlight.
    Size: 1200x630 px, with cover in background and styled quote.
    """
    book = Book.query.get_or_404(book_id)
    h = Highlight.query.filter_by(id=highlight_id, book_id=book.id).first_or_404()

    width, height = 1200, 630
    bg = Image.new('RGB', (width, height), (68, 88, 90))  # Dark Slate Grey base

    # Try to load cover as background
    cover_img = None
    try:
        import requests as _rq
        r = _rq.get(url_for('books.cover_image', book_id=book.id, raw=1, _external=True), timeout=10)
        if r.ok:
            cover_img = Image.open(BytesIO(r.content)).convert('RGB')
    except Exception:
        cover_img = None

    if cover_img:
        # Scale to fill
        c_w, c_h = cover_img.size
        scale = max(width / c_w, height / c_h)
        resized = cover_img.resize((int(c_w * scale), int(c_h * scale)))
        # center crop
        x0 = (resized.width - width) // 2
        y0 = (resized.height - height) // 2
        bg.paste(resized.crop((x0, y0, x0 + width, y0 + height)), (0, 0))

    # Overlay for contrast (Graphite with alpha)
    overlay = Image.new('RGBA', (width, height), (51, 46, 40, 160))
    bg = Image.alpha_composite(bg.convert('RGBA'), overlay)

    # Prepare to draw on composited image
    draw = ImageDraw.Draw(bg)

    # Quote text
    quote_font = _load_font(48)
    meta_font = _load_font(24)
    margin = 80
    max_text_width = width - margin * 2
    text = (h.text or '').strip()
    # Use a separate context for measuring
    measure_draw = ImageDraw.Draw(Image.new('RGB', (width, height)))
    text_wrapped = _wrap_text(measure_draw, text, quote_font, max_text_width)
    y = 140
    # Draw opening and closing quotes and text
    quote_color = (240, 248, 211)  # Light Yellow
    draw.text((margin, y - 40), '“', font=_load_font(72), fill=quote_color)
    draw.multiline_text((margin, y), text_wrapped, font=quote_font, fill=quote_color, spacing=8)

    # Footer bar (Emerald)
    footer_h = 70
    footer = Image.new('RGBA', (width, footer_h), (102, 185, 126, 255))
    bg.paste(footer, (0, height - footer_h))

    # Meta text on footer
    meta_color = (51, 46, 40)  # Graphite
    meta_y = height - footer_h + 20
    meta_x = 20
    title_txt = (book.clean_title or book.raw_title or '').strip()
    author_txt = (book.clean_authors or book.raw_authors or '').strip()
    meta_parts = [p for p in [title_txt, author_txt] if p]
    extras = []
    if h.page_number:
      extras.append(f"Page {h.page_number}")
    if h.chapter:
      extras.append(h.chapter)
    if h.datetime:
      extras.append(h.datetime)
    if extras:
        meta_parts.extend(extras)
    meta_text = ' • '.join(meta_parts)
    draw.text((meta_x, meta_y), meta_text, font=meta_font, fill=meta_color)

    # Logo at bottom-right
    try:
        from pathlib import Path
        logo_path = Path(current_app.root_path).parent / 'assets' / 'logo.png'
        if logo_path.exists():
            logo = Image.open(logo_path).convert('RGBA')
            # Resize to target height
            target_h = 40
            scale = target_h / logo.size[1]
            logo = logo.resize((int(logo.size[0] * scale), target_h))
            bg.paste(logo, (width - logo.size[0] - 20, height - footer_h + (footer_h - target_h)//2), logo)
    except Exception:
        pass

    # Output PNG
    out = BytesIO()
    bg.convert('RGB').save(out, format='PNG')
    out.seek(0)
    safe_title = (title_txt or 'quote').replace(' ', '_')
    return send_file(out, mimetype='image/png', as_attachment=True, download_name=f"{safe_title}-{h.id}.png")


@bp.post('/books/<int:book_id>/image-upload')
def book_image_upload(book_id: int):
    book = Book.query.get_or_404(book_id)
    f = request.files.get('file')
    if not f or not f.filename:
        return redirect(url_for('books.book_detail', book_id=book.id))
    content = f.read()
    content_type = f.mimetype or 'image/jpeg'
    if save_image_to_book(book, content, content_type):
        db.session.add(book)
        db.session.commit()
        flash('Cover image uploaded and saved to database.', 'success')
    else:
        flash('Failed to upload cover image.', 'danger')
    return redirect(url_for('books.book_detail', book_id=book.id))


@bp.post('/books/<int:book_id>/image-fetch')
def book_image_fetch(book_id: int):
    book = Book.query.get_or_404(book_id)
    remote = (request.form.get('image_fetch_url') or '').strip()
    if not remote:
        return redirect(url_for('books.book_detail', book_id=book.id))

    result = fetch_image_from_url(remote)
    if result:
        image_data, content_type = result
        if save_image_to_book(book, image_data, content_type):
            db.session.add(book)
            db.session.commit()
            flash('Cover image fetched and saved to database.', 'success')
        else:
            flash('Failed to save image to database.', 'danger')
    else:
        flash('Failed to fetch image from URL.', 'danger')
    return redirect(url_for('books.book_detail', book_id=book.id))


@bp.post('/admin/migrate-images-to-database')
def migrate_images_to_database():
    """Migrate all external image URLs to database blobs.
    This is an admin utility to convert legacy external URLs to database-stored images.
    """
    # Find all books with image_url but no image_data
    books_to_migrate = Book.query.filter(
        Book.image_url.isnot(None),
        Book.image_data.is_(None)
    ).all()

    if not books_to_migrate:
        flash('No external image URLs to migrate. All images already in database!', 'info')
        return redirect(url_for('books.index'))

    migrated = 0
    failed = 0

    for book in books_to_migrate:
        if not book.image_url:
            continue

        try:
            result = fetch_image_from_url(book.image_url)
            if result:
                image_data, content_type = result
                if save_image_to_book(book, image_data, content_type):
                    db.session.add(book)
                    migrated += 1
                else:
                    failed += 1
                    current_app.logger.warning(f'Failed to save image for book {book.id}')
            else:
                failed += 1
                current_app.logger.warning(f'Failed to fetch image for book {book.id}: {book.image_url}')
        except Exception as e:
            failed += 1
            current_app.logger.error(f'Error migrating image for book {book.id}: {e}')

    # Commit all changes at once
    db.session.commit()

    if migrated > 0:
        flash(f'Successfully migrated {migrated} image(s) to database. {failed} failed.', 'success' if failed == 0 else 'warning')
    else:
        flash(f'Migration failed. Could not fetch any images.', 'danger')

    return redirect(url_for('books.index'))
