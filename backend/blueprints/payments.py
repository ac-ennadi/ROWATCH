from datetime import datetime, timedelta

from flask import Blueprint, g, jsonify, request

from config import PLAN_LIMITS, PLAN_PRICES
from models import AccountPayment, AccountSubscription, User, db
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
    duration = int(data.get("duration_months") or 1)
    method = data.get("method") or "dummy"
    if plan not in ("free", "pro", "studio"):
        return jsonify({"error": "Invalid plan"}), 400
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
    duration = int(data.get("duration_months") or 1)
    target = User.query.get(data.get("user_id")) if data.get("user_id") else User.query.filter_by(username=data.get("username")).first()
    if plan not in ("free", "pro", "studio"):
        return jsonify({"error": "Invalid plan"}), 400
    if not target:
        return jsonify({"error": "User not found"}), 404
    subscription = _set_subscription(target, plan, duration, "robux", data.get("note") or "")
    db.session.add(AccountPayment(user_id=target.id, plan=plan, duration=duration, method="robux", amount=0, status="completed"))
    db.session.commit()
    return jsonify({"ok": True, "username": target.username, "plan": plan, "expires_at": subscription.expires_at.isoformat() if subscription.expires_at else None})


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
