from flask import Blueprint, render_template, request, redirect, url_for, current_app, flash, Response, send_file
from .. import db
from ..models import Book, Highlight, MergedHighlight, MergedHighlightItem, AppConfig, HighlightDevice
from ..services.openlibrary import fetch_from_url as fetch_ol, search as ol_search
from ..services.imagestore import store_image_from_url, store_image_from_bytes
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont

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
    # If ?raw=1, proxy the image bytes to ensure same-origin for capture
    if request.args.get('raw') == '1':
        try:
            import requests as _rq
            r = _rq.get(book.image_url, timeout=10)
            if r.ok:
                ct = r.headers.get('Content-Type', 'image/jpeg')
                try:
                    current_app.logger.info('cover raw fetch ok: %s bytes from %s', len(r.content), book.image_url)
                except Exception:
                    pass
                return Response(r.content, mimetype=ct)
            else:
                current_app.logger.warning('cover raw fetch failed: %s %s', r.status_code, book.image_url)
        except Exception as e:
            current_app.logger.warning('cover raw fetch exception: %s for %s', e, book.image_url)
        # Return a transparent 1x1 PNG as a safe fallback to avoid 404 navigation
        import base64
        png_1x1 = base64.b64decode(
            b'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAuMBgB2c7i0AAAAASUVORK5CYII='
        )
        return Response(png_1x1, mimetype='image/png')

    if rustfs and not book.image_url.startswith(rustfs.rstrip('/')):
        stored = store_image_from_url(book.image_url, rustfs_base=rustfs)
        if stored:
            book.image_url = stored
            db.session.add(book)
            db.session.commit()
            return redirect(book.image_url)
    return redirect(book.image_url)


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
