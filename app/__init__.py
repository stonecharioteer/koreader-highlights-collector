import os
from flask import Flask
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

    db.init_app(app)

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
                    from .models import SourcePath, AppConfig
                    base = app.config.get("HIGHLIGHTS_BASE_PATH")
                    if base and not SourcePath.query.first() and os.path.exists(base):
                        default_label = os.path.basename(os.path.normpath(base)) or None
                        db.session.add(SourcePath(path=base, enabled=True, device_label=default_label))
                        db.session.commit()
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

    return app
