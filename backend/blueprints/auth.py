from datetime import datetime
import hashlib
import re
import secrets

from flask import Blueprint, current_app, g, jsonify, make_response, request
from werkzeug.security import check_password_hash, generate_password_hash

from models import AccountApiKey, User, db
from utils import create_token, login_required


auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


def valid_email(email):
    return re.match(r"^[^@]+@[^@]+\.[^@]+$", email)


def _session_response(payload, user, status=200):
    response = make_response(jsonify(payload))
    response.set_cookie(
        "token",
        create_token(user.id),
        httponly=True,
        samesite="Lax",
        max_age=int(current_app.config["JWT_EXPIRY"].total_seconds()),
    )
    return response, status


def _new_api_key(user, existing=None):
    raw = secrets.token_hex(32)
    now = datetime.utcnow()
    record = existing or AccountApiKey(user_id=user.id)
    record.key_hash = hashlib.sha256(raw.encode()).hexdigest()
    record.key_prefix = raw[:12]
    if existing:
        record.regenerated_at = now
    else:
        db.session.add(record)
    db.session.commit()
    return raw, record


def _key_metadata(record):
    return {
        "configured": record is not None,
        "masked_key": f"{record.key_prefix}..." if record else None,
        "created_at": record.created_at.isoformat() if record else None,
        "regenerated_at": record.regenerated_at.isoformat() if record and record.regenerated_at else None,
        "last_used_at": record.last_used_at.isoformat() if record and record.last_used_at else None,
    }


@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    tracking_consent = data.get("tracking_consent") is True
    if not username or not email or not password:
        return jsonify({"error": "All fields are required"}), 400
    if len(username) < 3:
        return jsonify({"error": "Username must be at least 3 characters"}), 400
    if not valid_email(email):
        return jsonify({"error": "Enter a valid email address"}), 400
    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400
    if not tracking_consent:
        return jsonify({"error": "You must consent to Studio activity tracking to create an account", "consent_required": True}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({"error": "Username is already taken"}), 409
    if User.query.filter_by(email=email).first():
        return jsonify({"error": "Email is already registered"}), 409
    user = User(
        username=username,
        email=email,
        password_hash=generate_password_hash(password),
        tracking_consent_at=datetime.utcnow(),
        tracking_consent_version=current_app.config["TRACKING_CONSENT_VERSION"],
    )
    db.session.add(user)
    db.session.commit()
    return _session_response({
        "ok": True, "username": user.username, "email": user.email,
    }, user, 201)


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    login_id = (data.get("username") or data.get("email") or "").strip()
    password = data.get("password") or ""
    if not login_id or not password:
        return jsonify({"error": "Username/email and password are required"}), 400
    user = User.query.filter_by(username=login_id).first()
    if not user:
        user = User.query.filter_by(email=login_id.lower()).first()
    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({"error": "Invalid credentials"}), 401
    return _session_response({
        "ok": True, "username": user.username, "email": user.email,
    }, user)


@auth_bp.route("/logout", methods=["POST"])
def logout():
    response = make_response(jsonify({"ok": True}))
    response.delete_cookie("token")
    return response


@auth_bp.route("/me", methods=["GET"])
@login_required
def me():
    return jsonify({
        "id": g.user.id,
        "username": g.user.username,
        "email": g.user.email,
        "is_admin": g.user.is_admin,
        "plan": g.user.account_plan,
        "plan_expires_at": g.user.account_plan_expires_at.isoformat() if g.user.account_plan_expires_at else None,
        "created_at": g.user.created_at.isoformat(),
        "session_days": current_app.config["SESSION_DAYS"],
        "tracking_consent_at": g.user.tracking_consent_at.isoformat() if g.user.tracking_consent_at else None,
        "tracking_consent_version": g.user.tracking_consent_version,
        "current_consent_version": current_app.config["TRACKING_CONSENT_VERSION"],
        "consent_required": not (g.user.tracking_consent_at and g.user.tracking_consent_version == current_app.config["TRACKING_CONSENT_VERSION"]),
    })


@auth_bp.route("/consent", methods=["POST"])
@login_required
def accept_consent():
    data = request.get_json(silent=True) or {}
    if data.get("accepted") is not True:
        return jsonify({"error": "You must check the consent box to continue", "consent_required": True}), 400
    g.user.tracking_consent_at = datetime.utcnow()
    g.user.tracking_consent_version = current_app.config["TRACKING_CONSENT_VERSION"]
    db.session.commit()
    return jsonify({
        "ok": True,
        "tracking_consent_at": g.user.tracking_consent_at.isoformat(),
        "tracking_consent_version": g.user.tracking_consent_version,
        "consent_required": False,
    })


@auth_bp.route("/me", methods=["PATCH"])
@login_required
def update_me():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or g.user.username).strip()
    email = (data.get("email") or g.user.email).strip().lower()
    if len(username) < 3:
        return jsonify({"error": "Username must be at least 3 characters"}), 400
    if not valid_email(email):
        return jsonify({"error": "Enter a valid email address"}), 400
    if User.query.filter(User.username == username, User.id != g.user.id).first():
        return jsonify({"error": "Username is already taken"}), 409
    if User.query.filter(User.email == email, User.id != g.user.id).first():
        return jsonify({"error": "Email is already registered"}), 409
    g.user.username = username
    g.user.email = email
    db.session.commit()
    return jsonify({"ok": True, "username": username, "email": email})


@auth_bp.route("/password", methods=["PUT"])
@login_required
def change_password():
    data = request.get_json(silent=True) or {}
    current_password = data.get("current_password") or ""
    password = data.get("password") or ""
    if not check_password_hash(g.user.password_hash, current_password):
        return jsonify({"error": "Current password is incorrect"}), 401
    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400
    g.user.password_hash = generate_password_hash(password)
    db.session.commit()
    return jsonify({"ok": True})


@auth_bp.route("/api-key", methods=["GET"])
@login_required
def api_key_status():
    return jsonify(_key_metadata(db.session.get(AccountApiKey, g.user.id)))


@auth_bp.route("/api-key", methods=["POST"])
@login_required
def ensure_api_key():
    existing = db.session.get(AccountApiKey, g.user.id)
    if existing:
        return jsonify(_key_metadata(existing))
    raw, record = _new_api_key(g.user)
    return jsonify({
        **_key_metadata(record),
        "api_key": raw,
        "warning": "This API key is shown once. Store it securely.",
    }), 201


@auth_bp.route("/api-key/regenerate", methods=["POST"])
@login_required
def regenerate_api_key():
    raw, record = _new_api_key(g.user, db.session.get(AccountApiKey, g.user.id))
    return jsonify({
        **_key_metadata(record),
        "api_key": raw,
        "warning": "The previous API key stopped working immediately.",
    })
