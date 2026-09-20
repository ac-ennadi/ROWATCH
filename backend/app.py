from pathlib import Path
from urllib.parse import urlsplit
import os
import threading
import time

from flask import Flask, jsonify, request, send_from_directory
from sqlalchemy import inspect, text

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

    if not app.config.get("TESTING"):
        for name in ("SECRET_KEY", "JWT_SECRET"):
            value = app.config.get(name)
            if not value or len(value) < 32 or value.startswith("change-this"):
                raise RuntimeError(f"{name} must be a unique random value of at least 32 characters")
    db.init_app(app)
    socket_origins = list(app.config.get("TRUSTED_ORIGINS") or ()) if app.config.get("CORS_ENABLED") else []
    socketio.init_app(app, cors_allowed_origins=socket_origins)

    with app.app_context():
        from blueprints.auth import auth_bp
        from blueprints.projects import plugin_projects_bp, projects_bp
        from blueprints.events import events_bp
        from blueprints.dashboard import dashboard_bp
        from blueprints.payments import payments_bp
        from blueprints.workspace import plugin_documents_bp, plugin_tasks_bp, workspace_bp

        app.register_blueprint(auth_bp)
        app.register_blueprint(projects_bp)
        app.register_blueprint(plugin_projects_bp)
        app.register_blueprint(events_bp)
        app.register_blueprint(dashboard_bp)
        app.register_blueprint(payments_bp)
        app.register_blueprint(workspace_bp)
        app.register_blueprint(plugin_tasks_bp)
        app.register_blueprint(plugin_documents_bp)

        # Versioned Studio API. Keep the original routes registered as the
        # permanent legacy contract for already-installed plugin versions.
        app.register_blueprint(events_bp, url_prefix="/api/v1/events", name_prefix="v1")
        app.register_blueprint(plugin_projects_bp, url_prefix="/api/v1/plugin", name_prefix="v1")
        app.register_blueprint(plugin_tasks_bp, url_prefix="/api/v1/tasks", name_prefix="v1")
        app.register_blueprint(plugin_documents_bp, url_prefix="/api/v1/documents", name_prefix="v1")
        db.create_all()
        ensure_tracking_consent_columns()
        ensure_session_heartbeat_schema()
        ensure_document_editor_column()
        ensure_document_link_schema()
        ensure_task_board_schema()
        migrate_legacy_project_plans()
        bootstrap_admin_account()

    @app.before_request
    def validate_browser_origin():
        origin = request.headers.get("Origin")
        if not origin:
            return None
        # HTTPS is commonly terminated by the reverse proxy. Compare the public
        # host and port rather than Flask's internal HTTP-facing scheme.
        if urlsplit(origin).netloc.lower() == request.host.lower():
            return None
        trusted = set(app.config.get("TRUSTED_ORIGINS") or ())
        if not app.config.get("CORS_ENABLED") or origin.rstrip("/") not in trusted:
            return jsonify({"error": "Untrusted request origin"}), 403

    @app.after_request
    def security_headers(response):
        origin = request.headers.get("Origin", "").rstrip("/")
        trusted = set(app.config.get("TRUSTED_ORIGINS") or ())
        if app.config.get("CORS_ENABLED") and origin and origin in trusted:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-API-Key, X-Project-ID"
            response.headers["Access-Control-Allow-Methods"] = "GET, HEAD, POST, PATCH, PUT, DELETE, OPTIONS"
            response.headers.add("Vary", "Origin")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' ws: wss:; object-src 'none'; base-uri 'self'; frame-ancestors 'none'")
        if request.is_secure:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        if request.path.startswith("/api/v1/"):
            response.headers.setdefault("X-RoWatch-API-Version", "1")
        elif request.path.startswith(("/api/events/", "/api/plugin/", "/api/tasks")):
            response.headers.setdefault("X-RoWatch-API-Version", "legacy")
        return response

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



def ensure_tracking_consent_columns():
    """Add consent audit fields to databases created before consent tracking."""
    columns = {column["name"] for column in inspect(db.engine).get_columns("users")}
    if "tracking_consent_at" not in columns:
        db.session.execute(text("ALTER TABLE users ADD COLUMN tracking_consent_at DATETIME"))
    if "tracking_consent_version" not in columns:
        db.session.execute(text("ALTER TABLE users ADD COLUMN tracking_consent_version VARCHAR(32)"))
    db.session.commit()

def ensure_task_board_schema():
    """Add board metadata and seed defaults for databases created before columns."""
    task_columns = {column["name"] for column in inspect(db.engine).get_columns("tasks")}
    if "column_id" not in task_columns:
        db.session.execute(text("ALTER TABLE tasks ADD COLUMN column_id VARCHAR(36)"))
    if "position" not in task_columns:
        db.session.execute(text("ALTER TABLE tasks ADD COLUMN position INTEGER NOT NULL DEFAULT 0"))
    db.session.commit()

    from models import Project, Task, TaskColumn
    defaults = ("Backlog", "To do", "In progress", "Done")
    for project in Project.query.all():
        columns = TaskColumn.query.filter_by(project_id=project.id).order_by(TaskColumn.position).all()
        if not columns:
            columns = [TaskColumn(project_id=project.id, name=name, position=index) for index, name in enumerate(defaults)]
            db.session.add_all(columns)
            db.session.flush()
        unplaced = Task.query.filter_by(project_id=project.id, column_id=None).order_by(Task.created_at).all()
        for index, task_item in enumerate(unplaced):
            task_item.column_id = columns[0].id
            task_item.position = index
    db.session.commit()


def ensure_session_heartbeat_schema():
    """Cap legacy abandoned sessions at their latest recorded plugin activity."""
    session_columns = {column["name"] for column in inspect(db.engine).get_columns("sessions")}
    if "last_heartbeat_at" not in session_columns:
        db.session.execute(text("ALTER TABLE sessions ADD COLUMN last_heartbeat_at DATETIME"))
        db.session.commit()

    from models import InstanceEvent, ScriptEvent, Session
    for session in Session.query.filter_by(ended_at=None).all():
        latest_script = db.session.query(db.func.max(ScriptEvent.occurred_at)).filter_by(session_id=session.id).scalar()
        latest_instance = db.session.query(db.func.max(InstanceEvent.occurred_at)).filter_by(session_id=session.id).scalar()
        last_signal = max((value for value in (session.last_heartbeat_at, latest_script, latest_instance, session.started_at) if value), default=session.started_at)
        session.last_heartbeat_at = last_signal
        session.ended_at = last_signal
    db.session.commit()


def ensure_document_link_schema():
    """Resolve wiki links for documents created before the relationship table existed."""
    from blueprints.workspace import _sync_project_document_links
    from models import Project

    for project in Project.query.all():
        _sync_project_document_links(project.id)
    db.session.commit()


def ensure_document_editor_column():
    """Add last-editor attribution to databases created before this field existed."""
    columns = {column["name"] for column in inspect(db.engine).get_columns("project_documents")}
    if "updated_by_id" not in columns:
        db.session.execute(text("ALTER TABLE project_documents ADD COLUMN updated_by_id VARCHAR(36)"))
        db.session.commit()


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
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")), debug=False)
