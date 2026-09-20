import jwt
import functools
from datetime import datetime, timedelta
from flask import request, jsonify, g, current_app
from models import AccountApiKey, User, Project, ProjectMember, db
import hashlib

def create_token(user_id):
    payload = {
        "sub": user_id,
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + current_app.config["JWT_EXPIRY"],
    }
    return jwt.encode(payload, current_app.config["JWT_SECRET"], algorithm="HS256")

def decode_token(token):
    return jwt.decode(token, current_app.config["JWT_SECRET"], algorithms=["HS256"])


def consent_is_current(user):
    return bool(
        user
        and user.tracking_consent_at
        and user.tracking_consent_version == current_app.config["TRACKING_CONSENT_VERSION"]
    )


def consent_required_response():
    return jsonify({
        "error": "You must accept the current Terms of Service and Privacy Policy to continue",
        "consent_required": True,
        "consent_version": current_app.config["TRACKING_CONSENT_VERSION"],
    }), 403

def login_required(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        token = None
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
        if not token:
            token = request.cookies.get("token")
        if not token:
            return jsonify({"error": "Unauthorized"}), 401
        try:
            payload = decode_token(token)
            g.user = User.query.get(payload["sub"])
            if not g.user:
                return jsonify({"error": "User not found"}), 401
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token expired"}), 401
        except Exception:
            return jsonify({"error": "Invalid token"}), 401
        consent_endpoints = {"auth.me", "auth.accept_consent"}
        if request.endpoint not in consent_endpoints and not consent_is_current(g.user):
            return consent_required_response()
        return f(*args, **kwargs)
    return wrapper

def admin_required(f):
    @functools.wraps(f)
    @login_required
    def wrapper(*args, **kwargs):
        if not g.user.is_admin:
            return jsonify({"error": "Admin only"}), 403
        return f(*args, **kwargs)
    return wrapper

def _account_from_api_key():
    raw_key = request.headers.get("X-API-Key", "")
    if not raw_key:
        return None
    record = AccountApiKey.query.filter_by(
        key_hash=hashlib.sha256(raw_key.encode()).hexdigest()
    ).first()
    if not record:
        return None
    record.last_used_at = datetime.utcnow()
    db.session.commit()
    return record.user


def account_api_key_required(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        user = _account_from_api_key()
        if not user:
            return jsonify({"error": "Invalid or missing account API key", "api_key_required": True}), 401
        if not consent_is_current(user):
            return consent_required_response()
        g.user = user
        return f(*args, **kwargs)
    return wrapper


def plugin_auth(f):
    """Authenticate Studio by account API key and selected project membership."""
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        user = _account_from_api_key()
        project_id = request.headers.get("X-Project-ID")
        if not user:
            return jsonify({"error": "Invalid or missing account API key", "api_key_required": True}), 401
        if not consent_is_current(user):
            return consent_required_response()
        if not project_id:
            return jsonify({"error": "Missing selected project ID"}), 400
        project = db.session.get(Project, project_id)
        if not project:
            return jsonify({"error": "Project not found"}), 404
        member = ProjectMember.query.filter_by(project_id=project.id, user_id=user.id).first()
        if not member:
            return jsonify({"error": "Your account is not a member of this project"}), 403
        g.project = project
        g.user = user
        g.member = member
        return f(*args, **kwargs)
    return wrapper


def project_access(role_required=None):
    """Decorator for web routes that need project access."""
    def decorator(f):
        @functools.wraps(f)
        @login_required
        def wrapper(*args, **kwargs):
            project_id = kwargs.get("project_id")
            project = Project.query.get(project_id)
            if not project:
                return jsonify({"error": "Project not found"}), 404
            member = ProjectMember.query.filter_by(
                project_id=project_id, user_id=g.user.id
            ).first()
            if not member:
                return jsonify({"error": "Access denied"}), 403
            if role_required == "admin" and member.role not in ("owner", "co_admin"):
                return jsonify({"error": "Admin required"}), 403
            if role_required == "owner" and member.role != "owner":
                return jsonify({"error": "Owner required"}), 403
            g.project = project
            g.member  = member
            return f(*args, **kwargs)
        return wrapper
    return decorator

def purge_old_data():
    """Delete script_events and sessions older than plan allows."""
    from models import Session, ScriptEvent
    for project in Project.query.all():
        days = project.history_days
        if days is None:
            continue
        cutoff = datetime.utcnow() - timedelta(days=days)
        old_sessions = Session.query.filter(
            Session.project_id == project.id,
            Session.started_at < cutoff
        ).all()
        for s in old_sessions:
            ScriptEvent.query.filter_by(session_id=s.id).delete()
            db.session.delete(s)
    db.session.commit()
