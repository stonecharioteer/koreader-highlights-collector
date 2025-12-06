from flask import Blueprint, render_template, request, redirect, url_for, current_app
from .. import db
from ..models import Book, Highlight, MergedHighlight, MergedHighlightItem, AppConfig
from ..services.openlibrary import fetch_from_url as fetch_ol, search as ol_search

bp = Blueprint('books', __name__)


@bp.route('/')
def index():
    q = request.args.get('q', '').strip()
    query = Book.query
    if q:
        like = f"%{q}%"
        query = query.filter((Book.clean_title.ilike(like)) | (Book.raw_title.ilike(like)))
    books = query.order_by(Book.clean_title.asc().nullslast(), Book.raw_title.asc()).limit(200).all()
    return render_template('books/list.html', books=books, q=q)


@bp.route('/books/<int:book_id>')
def book_detail(book_id: int):
    book = Book.query.get_or_404(book_id)
    from sqlalchemy import or_
    highlights = (
        Highlight.query
        .filter(
            Highlight.book_id == book.id,
            Highlight.kind.in_(['highlight','highlight_empty','highlight_no_position'])
        )
        .order_by(Highlight.page_number.asc())
        .all()
    )
    return render_template('books/detail.html', book=book, highlights=highlights, ol_results=None)


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
                    new_image_url = meta['image']
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
            book.image_url = meta['image']
        if meta.get('url'):
            book.goodreads_url = meta['url']
        db.session.add(book)
        db.session.commit()
    except Exception:
        pass
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
            book.image_url = meta['image']
        db.session.add(book)
        db.session.commit()
    except Exception:
        pass
    return redirect(url_for('books.book_detail', book_id=book.id))


@bp.post('/books/<int:book_id>/update')
def book_update_inline(book_id: int):
    book = Book.query.get_or_404(book_id)
    book.clean_title = (request.form.get('clean_title') or '').strip() or None
    book.clean_authors = (request.form.get('clean_authors') or '').strip() or None
    book.image_url = (request.form.get('image_url') or '').strip() or None
    db.session.add(book)
    db.session.commit()
    return redirect(url_for('books.book_detail', book_id=book.id))
