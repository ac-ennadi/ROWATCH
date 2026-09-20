from pathlib import Path
import os
import threading
import time

from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS

from config import Config
from models import db
from realtime import socketio


BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)

    CORS(app, supports_credentials=True)
    db.init_app(app)
    socketio.init_app(app)

    with app.app_context():
        from blueprints.auth import auth_bp
        from blueprints.projects import plugin_projects_bp, projects_bp
        from blueprints.events import events_bp
        from blueprints.dashboard import dashboard_bp
        from blueprints.payments import payments_bp
        from blueprints.workspace import workspace_bp, plugin_tasks_bp

        app.register_blueprint(auth_bp)
        app.register_blueprint(projects_bp)
        app.register_blueprint(plugin_projects_bp)
        app.register_blueprint(events_bp)
        app.register_blueprint(dashboard_bp)
        app.register_blueprint(payments_bp)
        app.register_blueprint(workspace_bp)
        app.register_blueprint(plugin_tasks_bp)
        db.create_all()
        migrate_legacy_project_plans()
        bootstrap_admin_account()

    @app.get("/health")
    def health():
        return jsonify({"ok": True, "service": "rowatch"})

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def frontend(path):
        # API routes are handled by blueprints above. Everything else is the SPA.
        candidate = FRONTEND_DIR / path
        if path and candidate.is_file():
            return send_from_directory(FRONTEND_DIR, path)
        return send_from_directory(FRONTEND_DIR, "index.html")

    return app


def bootstrap_admin_account():
    """Create or synchronize the admin account from environment variables."""
    from werkzeug.security import generate_password_hash
    from models import User

    username = os.environ.get("ROWATCH_ADMIN_USERNAME", "").strip()
    email = os.environ.get("ROWATCH_ADMIN_EMAIL", "").strip().lower()
    password = os.environ.get("ROWATCH_ADMIN_PASSWORD", "")
    if not username and not email and not password:
        return
    if not username or not email or len(password) < 12:
        raise RuntimeError("ROWATCH_ADMIN_USERNAME, ROWATCH_ADMIN_EMAIL, and a 12+ character ROWATCH_ADMIN_PASSWORD are required")
    by_username = User.query.filter_by(username=username).first()
    by_email = User.query.filter_by(email=email).first()
    if by_username and by_email and by_username.id != by_email.id:
        raise RuntimeError("Admin username and email belong to different accounts")
    user = by_username or by_email
    if not user:
        user = User(username=username, email=email, password_hash=generate_password_hash(password), is_admin=True)
        db.session.add(user)
    else:
        user.username = username
        user.email = email
        user.password_hash = generate_password_hash(password)
        user.is_admin = True
    db.session.commit()


def migrate_legacy_project_plans():
    """Move the best active legacy project plan to its owner once."""
    from datetime import datetime
    from models import AccountSubscription, Project, User

    now = datetime.utcnow()
    rank = {"free": 0, "pro": 1, "studio": 2}
    changed = False
    for user in User.query.all():
        if user.subscription:
            continue
        candidates = [project for project in Project.query.filter_by(owner_id=user.id).all()
                      if project.plan in ("pro", "studio")
                      and (not project.plan_expires_at or project.plan_expires_at > now)]
        if not candidates:
            continue
        best = max(candidates, key=lambda project: rank[project.plan])
        expiry_candidates = [project.plan_expires_at for project in candidates
                             if project.plan == best.plan and project.plan_expires_at]
        db.session.add(AccountSubscription(
            user_id=user.id,
            plan=best.plan,
            expires_at=max(expiry_candidates) if expiry_candidates else None,
            activated_by=best.plan_activated_by or "migration",
            note="Migrated from project-level billing",
        ))
        changed = True
    if changed:
        db.session.commit()


def start_purge_thread(app):
    def purge_loop():
        while True:
            time.sleep(86400)
            with app.app_context():
                from utils import purge_old_data
                purge_old_data()
                print("[RoWatch] old tracking data purged")

    threading.Thread(target=purge_loop, daemon=True).start()


if __name__ == "__main__":
    app = create_app()
    if os.environ.get("ROWATCH_DISABLE_PURGE") != "1":
        start_purge_thread(app)
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=os.environ.get("FLASK_DEBUG", "1") == "1")
