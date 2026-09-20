from datetime import datetime, timedelta
import hashlib
import re
import secrets

from flask import Blueprint, g, jsonify, request

from config import PLAN_LIMITS, PLAN_PRICES
from models import AccountPayment, AccountSubscription, UpgradeCode, User, db
from utils import login_required


payments_bp = Blueprint("payments", __name__, url_prefix="/payments")


def _plan_dict(name):
    limits = PLAN_LIMITS[name]
    data = {
        "name": name,
        "projects": limits["projects"],
        "members": limits["members"],
        "history_days": limits["history_days"],
        "co_admins": limits["co_admins"],
        "export": limits["export"],
        "tasks": limits["tasks"],
        "documents": limits["documents"],
    }
    if name == "free":
        data["monthly"] = 0
        data["yearly"] = 0
    else:
        data.update(PLAN_PRICES[name])
    return data


def _set_subscription(user, plan, duration, method, note=""):
    subscription = user.subscription
    if not subscription:
        subscription = AccountSubscription(user_id=user.id)
        db.session.add(subscription)
    now = datetime.utcnow()
    subscription.plan = plan
    subscription.activated_by = method
    subscription.note = note
    if plan == "free":
        subscription.expires_at = None
    elif subscription.expires_at and subscription.expires_at > now:
        subscription.expires_at += timedelta(days=duration * 30)
    else:
        subscription.expires_at = now + timedelta(days=duration * 30)
    return subscription


@payments_bp.route("/plans", methods=["GET"])
def list_plans():
    return jsonify({name: _plan_dict(name) for name in ("free", "pro", "studio")})


@payments_bp.route("/account", methods=["GET"])
@login_required
def account_plan():
    return jsonify({
        "plan": g.user.account_plan,
        "expires_at": g.user.account_plan_expires_at.isoformat() if g.user.account_plan_expires_at else None,
        "plans": {name: _plan_dict(name) for name in ("free", "pro", "studio")},
    })


@payments_bp.route("/checkout", methods=["POST"])
@login_required
def checkout():
    """Dummy account-level gateway. Body: {plan, duration_months, method}."""
    data = request.get_json(silent=True) or {}
    plan = data.get("plan")
    try:
        duration = int(data.get("duration_months") or 1)
    except (TypeError, ValueError):
        return jsonify({"error": "Duration must be a whole number"}), 400
    method = data.get("method") or "dummy"
    if plan not in ("free", "pro", "studio"):
        return jsonify({"error": "Invalid plan"}), 400
    if plan in ("pro", "studio"):
        return jsonify({"error": "A valid upgrade code is required for paid plans", "code_required": True}), 400
    if g.user.account_plan in ("pro", "studio"):
        return jsonify({"error": "Paid plans cannot be downgraded to Free. The account returns to Free only after the paid term expires."}), 409
    if duration not in (1, 3, 12):
        return jsonify({"error": "Duration must be 1, 3, or 12 months"}), 400

    if plan == "free":
        amount = 0
    elif duration == 12:
        amount = PLAN_PRICES[plan]["yearly"]
    else:
        amount = PLAN_PRICES[plan]["monthly"] * duration

    subscription = _set_subscription(g.user, plan, duration, method)
    db.session.add(AccountPayment(
        user_id=g.user.id,
        plan=plan,
        duration=duration,
        method=method,
        amount=amount,
        status="completed",
    ))
    db.session.commit()
    return jsonify({
        "ok": True,
        "plan": plan,
        "expires_at": subscription.expires_at.isoformat() if subscription.expires_at else None,
        "amount_charged": amount,
        "method": method,
        "message": "Account plan updated (dummy gateway)",
    })


@payments_bp.route("/admin/activate", methods=["POST"])
@login_required
def admin_activate():
    if not g.user.is_admin:
        return jsonify({"error": "Admin only"}), 403
    data = request.get_json(silent=True) or {}
    plan = data.get("plan")
    try:
        duration = int(data.get("duration_months") or 1)
    except (TypeError, ValueError):
        return jsonify({"error": "Duration must be a whole number"}), 400
    target = User.query.get(data.get("user_id")) if data.get("user_id") else User.query.filter_by(username=data.get("username")).first()
    if plan not in ("free", "pro", "studio"):
        return jsonify({"error": "Invalid plan"}), 400
    if not target:
        return jsonify({"error": "User not found"}), 404
    subscription = _set_subscription(target, plan, duration, "robux", data.get("note") or "")
    db.session.add(AccountPayment(user_id=target.id, plan=plan, duration=duration, method="robux", amount=0, status="completed"))
    db.session.commit()
    return jsonify({"ok": True, "username": target.username, "plan": plan, "expires_at": subscription.expires_at.isoformat() if subscription.expires_at else None})


def _code_dict(upgrade_code):
    return {
        "id": upgrade_code.id,
        "masked_code": f"{upgrade_code.code_prefix}…",
        "plan": upgrade_code.plan,
        "duration_days": upgrade_code.duration_days,
        "expires_at": upgrade_code.expires_at.isoformat() if upgrade_code.expires_at else None,
        "status": upgrade_code.status,
        "created_by": upgrade_code.created_by.username,
        "created_at": upgrade_code.created_at.isoformat(),
        "redeemed_by": upgrade_code.redeemed_by.username if upgrade_code.redeemed_by else None,
        "redeemed_at": upgrade_code.redeemed_at.isoformat() if upgrade_code.redeemed_at else None,
        "revoked_at": upgrade_code.revoked_at.isoformat() if upgrade_code.revoked_at else None,
        "note": upgrade_code.note or "",
    }


def _parse_code_expiry(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        raise ValueError("Invalid code expiration date")


@payments_bp.route("/codes", methods=["POST"])
@login_required
def create_codes():
    if not g.user.is_admin:
        return jsonify({"error": "Admin only"}), 403
    data = request.get_json(silent=True) or {}
    plan = data.get("plan")
    try:
        duration_days = int(data.get("duration_days") or 0)
        quantity = int(data.get("quantity") or 1)
    except (TypeError, ValueError):
        return jsonify({"error": "Duration and quantity must be whole numbers"}), 400
    if plan not in ("pro", "studio"):
        return jsonify({"error": "Codes can target Pro or Studio only"}), 400
    if duration_days < 1 or duration_days > 3650:
        return jsonify({"error": "Duration must be between 1 and 3650 days"}), 400
    if quantity < 1 or quantity > 100:
        return jsonify({"error": "Quantity must be between 1 and 100"}), 400
    try:
        expires_at = _parse_code_expiry(data.get("expires_at"))
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    if expires_at and expires_at <= datetime.utcnow():
        return jsonify({"error": "Code expiration must be in the future"}), 400

    generated = []
    for _ in range(quantity):
        raw_code = secrets.token_hex(32)
        record = UpgradeCode(
            code_hash=hashlib.sha256(raw_code.encode()).hexdigest(),
            code_prefix=raw_code[:8],
            plan=plan,
            duration_days=duration_days,
            expires_at=expires_at,
            created_by_id=g.user.id,
            note=str(data.get("note") or "")[:1000],
        )
        db.session.add(record)
        generated.append((raw_code, record))
    db.session.commit()
    return jsonify({
        "warning": "Raw codes are shown once. Store them securely.",
        "codes": [{"code": raw, **_code_dict(record)} for raw, record in generated],
    }), 201


@payments_bp.route("/codes", methods=["GET"])
@login_required
def list_codes():
    if not g.user.is_admin:
        return jsonify({"error": "Admin only"}), 403
    records = UpgradeCode.query.order_by(UpgradeCode.created_at.desc()).limit(500).all()
    return jsonify([_code_dict(record) for record in records])


@payments_bp.route("/codes/<code_id>/revoke", methods=["POST"])
@login_required
def revoke_code(code_id):
    if not g.user.is_admin:
        return jsonify({"error": "Admin only"}), 403
    record = db.session.get(UpgradeCode, code_id)
    if not record:
        return jsonify({"error": "Upgrade code not found"}), 404
    if record.redeemed_at:
        return jsonify({"error": "Redeemed codes cannot be revoked"}), 409
    if not record.revoked_at:
        record.revoked_at = datetime.utcnow()
        db.session.commit()
    return jsonify({"ok": True, "status": "revoked"})


@payments_bp.route("/codes/redeem", methods=["POST"])
@login_required
def redeem_code():
    raw_code = str((request.get_json(silent=True) or {}).get("code") or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", raw_code):
        return jsonify({"error": "Code must contain exactly 64 hexadecimal characters"}), 400
    code_hash = hashlib.sha256(raw_code.encode()).hexdigest()
    record = UpgradeCode.query.filter_by(code_hash=code_hash).first()
    if not record:
        return jsonify({"error": "Invalid upgrade code"}), 404
    now = datetime.utcnow()
    if record.revoked_at:
        return jsonify({"error": "This upgrade code was revoked"}), 409
    if record.redeemed_at:
        return jsonify({"error": "This upgrade code was already redeemed"}), 409
    if record.expires_at and record.expires_at <= now:
        return jsonify({"error": "This upgrade code has expired"}), 410
    current_plan = g.user.account_plan
    if current_plan == "studio" and record.plan == "pro":
        return jsonify({"error": "Studio accounts cannot downgrade to Pro"}), 409

    claimed = UpgradeCode.query.filter(
        UpgradeCode.id == record.id,
        UpgradeCode.redeemed_at.is_(None),
        UpgradeCode.revoked_at.is_(None),
    ).update({
        UpgradeCode.redeemed_by_id: g.user.id,
        UpgradeCode.redeemed_at: now,
    }, synchronize_session=False)
    if claimed != 1:
        db.session.rollback()
        return jsonify({"error": "This upgrade code is no longer available"}), 409

    subscription = g.user.subscription
    if not subscription:
        subscription = AccountSubscription(user_id=g.user.id)
        db.session.add(subscription)
    base = subscription.expires_at if subscription.expires_at and subscription.expires_at > now else now
    subscription.plan = record.plan
    subscription.expires_at = base + timedelta(days=record.duration_days)
    subscription.activated_by = "upgrade_code"
    subscription.note = f"Redeemed code {record.code_prefix}…"
    db.session.add(AccountPayment(
        user_id=g.user.id,
        plan=record.plan,
        duration=max(1, (record.duration_days + 29) // 30),
        method="upgrade_code",
        amount=0,
        status="completed",
    ))
    db.session.commit()
    return jsonify({
        "ok": True,
        "plan": subscription.plan,
        "duration_days": record.duration_days,
        "expires_at": subscription.expires_at.isoformat(),
    })


@payments_bp.route("/history", methods=["GET"])
@login_required
def payment_history():
    payments = AccountPayment.query.filter_by(user_id=g.user.id).order_by(AccountPayment.created_at.desc()).all()
    return jsonify([{
        "id": payment.id,
        "plan": payment.plan,
        "duration": payment.duration,
        "method": payment.method,
        "amount": payment.amount,
        "status": payment.status,
        "created_at": payment.created_at.isoformat(),
    } for payment in payments])
