import os
from pathlib import Path
from flask import Flask, render_template, send_from_directory, abort
import time
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def create_app() -> Flask:
    app = Flask(__name__)

    app.config.setdefault("SQLALCHEMY_DATABASE_URI", os.getenv("DATABASE_URL", "sqlite:///app.db"))
    app.config.setdefault("SQLALCHEMY_TRACK_MODIFICATIONS", False)
    app.config.setdefault("SQLALCHEMY_ENGINE_OPTIONS", {"pool_pre_ping": True})
    app.config.setdefault("HIGHLIGHTS_BASE_PATH", os.getenv("HIGHLIGHTS_BASE_PATH", str((os.getcwd() + "/sample-highlights"))))
    app.config.setdefault("CELERY_BROKER_URL", os.getenv("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672//"))
    app.config.setdefault("CELERY_RESULT_BACKEND", os.getenv("CELERY_RESULT_BACKEND", "rpc://"))
    app.config.setdefault("RUSTFS_URL", os.getenv("RUSTFS_URL"))
    # Required for flash messages and sessions. Treat empty as unset.
    _sk = os.getenv("SECRET_KEY")
    if not _sk:
        _sk = "dev-secret-key"
    app.config["SECRET_KEY"] = _sk

    db.init_app(app)

    # Register custom Jinja filters
    @app.template_filter('humandate')
    def humandate_filter(date_str):
        """Convert datetime string to human-readable format with time."""
        if not date_str:
            return ''
        try:
            from datetime import datetime
            # Parse KOReader datetime format: YYYY-MM-DD HH:MM:SS
            dt = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
            # Format as: "Jun 30, 2025 at 6:15 PM"
            # Use %I instead of %-I for cross-platform compatibility, then strip leading zero
            time_str = dt.strftime('%b %d, %Y at %I:%M %p')
            # Remove leading zero from hour (e.g., "06:15" -> "6:15")
            return time_str.replace(' 0', ' ')
        except (ValueError, AttributeError):
            # If parsing fails, return original
            return date_str

    @app.template_filter('humandate_short')
    def humandate_short_filter(date_str):
        """Convert datetime string to short date format (no time)."""
        if not date_str:
            return ''
        try:
            from datetime import datetime
            # Try parsing full datetime format first: YYYY-MM-DD HH:MM:SS
            try:
                dt = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                # Try parsing date-only format: YYYY-MM-DD
                dt = datetime.strptime(date_str, '%Y-%m-%d')
            # Format as: "Jun 30, 2025"
            return dt.strftime('%b %d, %Y')
        except (ValueError, AttributeError):
            # If parsing fails, return original
            return date_str

    # Create tables on startup for convenience (no Alembic yet)
    with app.app_context():
        from . import models  # noqa: F401
        # Wait for DB to be ready
        last_err = None
        for _ in range(30):
            try:
                db.create_all()
                # Seed a default source path if DB is empty and config path exists
                try:
                    from .models import AppConfig
                    # Ensure one AppConfig row exists
                    if not AppConfig.query.first():
                        db.session.add(AppConfig())
                        db.session.commit()
                except Exception:
                    pass
                last_err = None
                break
            except Exception as e:
                last_err = e
                time.sleep(1)
        if last_err:
            raise last_err

    # Register blueprints
    from .views.books import bp as books_bp
    from .views.tasks import bp as tasks_bp
    from .views.config import bp as config_bp
    app.register_blueprint(books_bp)
    app.register_blueprint(tasks_bp)
    app.register_blueprint(config_bp)

    # Error pages
    @app.errorhandler(404)
    def not_found(e):
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def server_error(e):
        return render_template('errors/500.html'), 500

    @app.get('/assets/<path:filename>')
    def assets_file(filename: str):
        # Serve files from repository-level assets folder, then fallback to repo root
        repo_root = Path(app.root_path).parent
        assets_dir = repo_root / 'assets'
        candidates = [assets_dir / filename, repo_root / filename]
        for fp in candidates:
            if fp.exists():
                return send_from_directory(fp.parent.as_posix(), fp.name)
        abort(404)

    @app.get('/assets/banner')
    def assets_banner():
        # Serve a banner image with flexible extensions
        repo_root = Path(app.root_path).parent
        assets_dir = repo_root / 'assets'
        names = ['banner.png', 'banner.jpg', 'banner.jpeg', 'banner.webp', 'banner.gif', 'banner.svg']
        for name in names:
            for base in (assets_dir, repo_root):
                fp = base / name
                if fp.exists():
                    return send_from_directory(fp.parent.as_posix(), fp.name)
        abort(404)

    return app
