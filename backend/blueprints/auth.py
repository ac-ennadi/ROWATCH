from flask import Blueprint, request, jsonify, make_response, g
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User
from utils import create_token, login_required
import re


auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


def valid_email(email):
    return re.match(r"^[^@]+@[^@]+\.[^@]+$", email)


@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not username or not email or not password:
        return jsonify({"error": "All fields are required"}), 400
    if len(username) < 3:
        return jsonify({"error": "Username must be at least 3 characters"}), 400
    if not valid_email(email):
        return jsonify({"error": "Enter a valid email address"}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({"error": "Username is already taken"}), 409
    if User.query.filter_by(email=email).first():
        return jsonify({"error": "Email is already registered"}), 409

    user = User(username=username, email=email, password_hash=generate_password_hash(password))
    db.session.add(user)
    db.session.commit()

    token = create_token(user.id)
    resp = make_response(jsonify({"ok": True, "username": user.username, "email": user.email}))
    resp.set_cookie("token", token, httponly=True, samesite="Lax", max_age=60 * 60 * 24 * 7)
    return resp, 201


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    login_id = (data.get("username") or data.get("email") or "").strip()
    password = data.get("password") or ""

    if not login_id or not password:
        return jsonify({"error": "Username/email and password are required"}), 400

    user = User.query.filter_by(username=login_id).first() or User.query.filter_by(email=login_id.lower()).first()
    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({"error": "Invalid credentials"}), 401

    token = create_token(user.id)
    resp = make_response(jsonify({"ok": True, "username": user.username, "email": user.email}))
    resp.set_cookie("token", token, httponly=True, samesite="Lax", max_age=60 * 60 * 24 * 7)
    return resp


@auth_bp.route("/logout", methods=["POST"])
def logout():
    resp = make_response(jsonify({"ok": True}))
    resp.delete_cookie("token")
    return resp


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

    username_owner = User.query.filter(User.username == username, User.id != g.user.id).first()
    email_owner = User.query.filter(User.email == email, User.id != g.user.id).first()
    if username_owner:
        return jsonify({"error": "Username is already taken"}), 409
    if email_owner:
        return jsonify({"error": "Email is already registered"}), 409

    g.user.username = username
    g.user.email = email
    db.session.commit()
    return jsonify({"ok": True, "username": username, "email": email})
