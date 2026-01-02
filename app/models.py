from datetime import datetime
from . import db


class TimestampMixin:
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class Book(db.Model, TimestampMixin):
    __tablename__ = "books"
    id = db.Column(db.Integer, primary_key=True)
    checksum = db.Column(db.String(64), index=True)  # partial_md5_checksum or path hash
    raw_title = db.Column(db.String)
    raw_authors = db.Column(db.String)
    identifiers = db.Column(db.String)
    language = db.Column(db.String)
    description = db.Column(db.Text)
    file_path = db.Column(db.Text)

    clean_title = db.Column(db.String)
    clean_authors = db.Column(db.String)
    goodreads_url = db.Column(db.String)
    image_url = db.Column(db.String)  # Deprecated: use image_data instead
    image_data = db.Column(db.LargeBinary, nullable=True)  # Store image as blob
    image_content_type = db.Column(db.String(100), nullable=True)  # e.g., 'image/jpeg'

    highlights = db.relationship(
        "Highlight", backref="book", cascade="all, delete-orphan"
    )
    notes = db.relationship("Note", backref="book", cascade="all, delete-orphan")
    bookmarks = db.relationship(
        "Bookmark", backref="book", cascade="all, delete-orphan"
    )
    merged = db.relationship(
        "MergedHighlight", backref="book", cascade="all, delete-orphan"
    )


class Highlight(db.Model, TimestampMixin):
    __tablename__ = "highlights"
    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(
        db.Integer, db.ForeignKey("books.id"), index=True, nullable=False
    )
    text = db.Column(db.Text)
    chapter = db.Column(db.String)
    page_number = db.Column(db.Integer)
    datetime = db.Column(db.String)
    color = db.Column(db.String)
    drawer = db.Column(db.String)
    device_id = db.Column(db.String)
    page_xpath = db.Column(db.Text)
    kind = db.Column(db.String, default="highlight")  # highlight, bookmark, note, etc.
    hidden = db.Column(
        db.Boolean, default=False, nullable=False, index=True
    )  # hide from UI
    devices = db.relationship(
        "HighlightDevice", backref="highlight", cascade="all, delete-orphan"
    )


class Note(db.Model, TimestampMixin):
    __tablename__ = "notes"
    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(
        db.Integer, db.ForeignKey("books.id"), index=True, nullable=False
    )
    text = db.Column(db.Text)
    datetime = db.Column(db.String)
    device_id = db.Column(db.String)


class Bookmark(db.Model, TimestampMixin):
    __tablename__ = "bookmarks"
    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(
        db.Integer, db.ForeignKey("books.id"), index=True, nullable=False
    )
    chapter = db.Column(db.String)
    page_number = db.Column(db.Integer)
    datetime = db.Column(db.String)
    device_id = db.Column(db.String)


class MergedHighlight(db.Model, TimestampMixin):
    __tablename__ = "merged_highlights"
    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(
        db.Integer, db.ForeignKey("books.id"), index=True, nullable=False
    )
    text = db.Column(db.Text)
    notes = db.Column(db.Text)
    items = db.relationship(
        "MergedHighlightItem", backref="merged", cascade="all, delete-orphan"
    )


class MergedHighlightItem(db.Model):
    __tablename__ = "merged_highlight_items"
    id = db.Column(db.Integer, primary_key=True)
    merged_id = db.Column(
        db.Integer, db.ForeignKey("merged_highlights.id"), index=True, nullable=False
    )
    highlight_id = db.Column(
        db.Integer, db.ForeignKey("highlights.id"), index=True, nullable=False
    )


class HighlightDevice(db.Model):
    __tablename__ = "highlight_devices"
    id = db.Column(db.Integer, primary_key=True)
    highlight_id = db.Column(
        db.Integer, db.ForeignKey("highlights.id"), index=True, nullable=False
    )
    device_id = db.Column(db.String, nullable=False)
    __table_args__ = (
        db.UniqueConstraint("highlight_id", "device_id", name="uq_highlight_device"),
    )


class SourcePath(db.Model, TimestampMixin):
    __tablename__ = "source_paths"
    id = db.Column(db.Integer, primary_key=True)
    path = db.Column(db.Text, nullable=False, unique=True)
    enabled = db.Column(db.Boolean, default=True, nullable=False)
    device_label = db.Column(db.String(200), nullable=True)


class AppConfig(db.Model, TimestampMixin):
    __tablename__ = "app_config"
    id = db.Column(db.Integer, primary_key=True)
    goodreads_api_key = db.Column(db.Text, nullable=True)  # legacy, unused
    ol_app_name = db.Column(db.String(100), nullable=True)
    ol_contact_email = db.Column(db.String(200), nullable=True)
    scan_schedule = db.Column(
        db.String(100), nullable=True, default="*/15 * * * *"
    )  # cron syntax, default: every 15 minutes
    job_retention_days = db.Column(
        db.Integer, nullable=False, default=30
    )  # Delete jobs older than this many days


class ExportTemplate(db.Model, TimestampMixin):
    __tablename__ = "export_templates"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    template_content = db.Column(db.Text, nullable=False)
    is_default = db.Column(db.Boolean, default=False, nullable=False)
    # Jinja2 templates for filenames - variables: book_title, book_authors, export_date
    filename_template = db.Column(
        db.String(500), nullable=False, default="{{ book_title }}.md"
    )
    cover_filename_template = db.Column(
        db.String(500), nullable=False, default="{{ book_title }}"
    )


class Job(db.Model, TimestampMixin):
    __tablename__ = "jobs"
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(
        db.String(100), unique=True, nullable=False, index=True
    )  # UUID or task ID
    job_type = db.Column(
        db.String(50), nullable=False, index=True
    )  # scan, export, etc.
    status = db.Column(
        db.String(50), default="pending", nullable=False, index=True
    )  # pending, processing, completed, failed
    error_message = db.Column(db.Text, nullable=True)
    result_summary = db.Column(db.Text, nullable=True)  # JSON summary of results
    completed_at = db.Column(db.DateTime, nullable=True)


class ExportJob(db.Model, TimestampMixin):
    __tablename__ = "export_jobs"
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(
        db.String(100), unique=True, nullable=False, index=True
    )  # UUID for the job
    book_id = db.Column(
        db.Integer, db.ForeignKey("books.id"), index=True, nullable=False
    )
    template_id = db.Column(
        db.Integer, db.ForeignKey("export_templates.id"), nullable=False
    )
    highlight_ids = db.Column(db.Text, nullable=False)  # JSON array of highlight IDs
    status = db.Column(
        db.String(50), default="pending", nullable=False
    )  # pending, processing, completed, failed
    error_message = db.Column(db.Text, nullable=True)
    file_path = db.Column(db.Text, nullable=True)  # Path to generated zip file
    completed_at = db.Column(db.DateTime, nullable=True)

    book = db.relationship("Book", backref="export_jobs")
    template = db.relationship("ExportTemplate", backref="export_jobs")
