from pathlib import Path
import os
from flask import Blueprint, render_template, request, redirect, url_for, jsonify
from .. import db
from ..models import SourcePath, AppConfig

bp = Blueprint('config', __name__)


@bp.route('/config', methods=['GET', 'POST'])
def index():
    # Ensure a config row exists
    cfg = AppConfig.query.first()
    if not cfg:
        cfg = AppConfig()
        db.session.add(cfg)
        db.session.commit()

    if request.method == 'POST':
        if 'path' in request.form:
            path = (request.form.get('path') or '').strip()
            raw_label = (request.form.get('device_label') or '').strip()
            device_label = raw_label or (os.path.basename(os.path.normpath(path)) if path else None)
            if path:
                sp = SourcePath.query.filter_by(path=path).first()
                if not sp:
                    sp = SourcePath(path=path, enabled=True, device_label=device_label)
                    db.session.add(sp)
                    db.session.commit()
            return redirect(url_for('config.index'))

        if 'ol_app_name' in request.form or 'ol_contact_email' in request.form:
            cfg.ol_app_name = (request.form.get('ol_app_name') or '').strip() or None
            cfg.ol_contact_email = (request.form.get('ol_contact_email') or '').strip() or None
            db.session.add(cfg)
            db.session.commit()
            return redirect(url_for('config.index'))

    paths = SourcePath.query.order_by(SourcePath.enabled.desc(), SourcePath.path.asc()).all()
    return render_template('config/index.html', paths=paths, cfg=cfg)


@bp.get('/config/suggest')
def suggest_paths():
    """Return directory suggestions for a given path prefix.
    Query params:
      - prefix: the partial path typed by the user
    """
    prefix = (request.args.get('prefix') or '').strip()
    if not prefix:
        # Suggest common roots inside container
        candidates = ["/", "/data", "/data/highlights"]
        return jsonify({"paths": candidates})

    # Expand ~ and normpath
    expanded = os.path.expanduser(prefix)

    # Decide base dir and needle
    if expanded.endswith(os.sep):
        base_dir = expanded
        needle = ''
    else:
        base_dir = os.path.dirname(expanded) or '/'
        needle = os.path.basename(expanded)

    results = []
    try:
        for name in os.listdir(base_dir or '/'):  # base_dir may be ''
            if needle and not name.startswith(needle):
                continue
            full = os.path.join(base_dir, name)
            try:
                if os.path.isdir(full):
                    results.append(full)
            except Exception:
                continue
            if len(results) >= 50:
                break
    except Exception:
        # Fallback: no suggestions
        pass

    return jsonify({"paths": sorted(results)})


@bp.route('/config/paths/<int:pid>/toggle', methods=['POST'])
def toggle(pid: int):
    sp = SourcePath.query.get_or_404(pid)
    sp.enabled = not sp.enabled
    db.session.add(sp)
    db.session.commit()
    return redirect(url_for('config.index'))


@bp.route('/config/paths/<int:pid>/delete', methods=['POST'])
def delete(pid: int):
    sp = SourcePath.query.get_or_404(pid)
    db.session.delete(sp)
    db.session.commit()
    return redirect(url_for('config.index'))


@bp.route('/config/paths/<int:pid>/label', methods=['POST'])
def update_label(pid: int):
    sp = SourcePath.query.get_or_404(pid)
    raw_label = (request.form.get('device_label') or '').strip()
    sp.device_label = raw_label or os.path.basename(os.path.normpath(sp.path))
    db.session.add(sp)
    db.session.commit()
    return redirect(url_for('config.index'))
