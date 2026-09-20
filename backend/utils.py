import jwt
import functools
from datetime import datetime, timedelta
from flask import request, jsonify, g, current_app
from models import User, Project, ProjectMember, db

def create_token(user_id):
    payload = {
        "sub": user_id,
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(days=7),
    }
    return jwt.encode(payload, current_app.config["JWT_SECRET"], algorithm="HS256")

def decode_token(token):
    return jwt.decode(token, current_app.config["JWT_SECRET"], algorithms=["HS256"])

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

def plugin_auth(f):
    """Authenticate plugin requests via X-Project-Key + X-Username headers."""
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        key      = request.headers.get("X-Project-Key")
        username = request.headers.get("X-Username")
        if not key or not username:
            return jsonify({"error": "Missing X-Project-Key or X-Username"}), 401
        project = Project.query.filter_by(project_key=key).first()
        if not project:
            return jsonify({"error": "Invalid project key"}), 401
        user = User.query.filter_by(username=username).first()
        if not user:
            return jsonify({"error": "Unknown username"}), 401
        member = ProjectMember.query.filter_by(project_id=project.id, user_id=user.id).first()
        if not member:
            return jsonify({"error": "Not a member of this project"}), 403
        g.project = project
        g.user    = user
        g.member  = member
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
