from flask import Blueprint, request, jsonify, g
from models import db, Project, Payment
from utils import login_required, project_access
from config import PLAN_PRICES
from datetime import datetime, timedelta

payments_bp = Blueprint("payments", __name__, url_prefix="/payments")

PLAN_DURATIONS = {1: "1 month", 3: "3 months", 12: "1 year"}

@payments_bp.route("/plans", methods=["GET"])
def list_plans():
    return jsonify({
        "free": {
            "price": 0,
            "projects":    1,
            "members":     5,
            "history":     "7 days",
            "co_admins":   0,
            "export":      False,
        },
        "pro": {
            "monthly":  PLAN_PRICES["pro"]["monthly"],
            "yearly":   PLAN_PRICES["pro"]["yearly"],
            "projects":    3,
            "members":     15,
            "history":     "2 months",
            "co_admins":   1,
            "export":      True,
        },
        "studio": {
            "monthly":  PLAN_PRICES["studio"]["monthly"],
            "yearly":   PLAN_PRICES["studio"]["yearly"],
            "projects":  "unlimited",
            "members":   "unlimited",
            "history":   "unlimited",
            "co_admins": "unlimited",
            "export":    True,
        },
    })

@payments_bp.route("/checkout", methods=["POST"])
@login_required
def checkout():
    """
    Dummy gateway — accepts all payments instantly.
    Body: { project_id, plan, duration_months, method }
    """
    data       = request.get_json(silent=True) or {}
    project_id = data.get("project_id")
    plan       = data.get("plan")
    duration   = int(data.get("duration_months") or 1)
    method     = data.get("method") or "dummy"

    if plan not in ("pro", "studio"):
        return jsonify({"error": "Invalid plan"}), 400
    if duration not in (1, 3, 12):
        return jsonify({"error": "Duration must be 1, 3, or 12 months"}), 400

    project = Project.query.get(project_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404
    if project.owner_id != g.user.id:
        return jsonify({"error": "Only owner can upgrade"}), 403

    # Calculate price
    if duration == 12:
        amount = PLAN_PRICES[plan]["yearly"]
    else:
        amount = PLAN_PRICES[plan]["monthly"] * duration

    # ── DUMMY GATEWAY: always succeeds ──
    payment = Payment(
        project_id=project_id,
        plan=plan,
        duration=duration,
        method=method,
        amount=amount,
        status="completed",
    )
    db.session.add(payment)

    # Activate plan
    now = datetime.utcnow()
    if project.plan_expires_at and project.plan_expires_at > now:
        # extend existing plan
        project.plan_expires_at += timedelta(days=duration * 30)
    else:
        project.plan_expires_at = now + timedelta(days=duration * 30)

    project.plan              = plan
    project.plan_activated_by = method
    db.session.commit()

    return jsonify({
        "ok":             True,
        "plan":           plan,
        "expires_at":     project.plan_expires_at.isoformat(),
        "amount_charged": amount,
        "method":         method,
        "message":        "Payment accepted (dummy gateway)",
    })

@payments_bp.route("/admin/activate", methods=["POST"])
@login_required
def admin_activate():
    """Manual activation for Robux payments (site admin only)."""
    if not g.user.is_admin:
        return jsonify({"error": "Admin only"}), 403

    data       = request.get_json(silent=True) or {}
    project_id = data.get("project_id")
    plan       = data.get("plan")
    duration   = int(data.get("duration_months") or 1)
    note       = data.get("note") or ""

    if plan not in ("pro", "studio"):
        return jsonify({"error": "Invalid plan"}), 400

    project = Project.query.get(project_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    now = datetime.utcnow()
    if project.plan_expires_at and project.plan_expires_at > now:
        project.plan_expires_at += timedelta(days=duration * 30)
    else:
        project.plan_expires_at = now + timedelta(days=duration * 30)

    project.plan              = plan
    project.plan_activated_by = "robux"
    project.plan_note         = note

    payment = Payment(
        project_id=project_id,
        plan=plan,
        duration=duration,
        method="robux",
        amount=0,
        status="completed",
    )
    db.session.add(payment)
    db.session.commit()

    return jsonify({
        "ok":         True,
        "plan":       plan,
        "expires_at": project.plan_expires_at.isoformat(),
        "note":       note,
    })

@payments_bp.route("/history/<project_id>", methods=["GET"])
@login_required
def payment_history(project_id):
    project = Project.query.get(project_id)
    if not project or project.owner_id != g.user.id:
        return jsonify({"error": "Access denied"}), 403

    payments = Payment.query.filter_by(project_id=project_id)\
                            .order_by(Payment.created_at.desc()).all()
    return jsonify([{
        "id":         p.id,
        "plan":       p.plan,
        "duration":   p.duration,
        "method":     p.method,
        "amount":     p.amount,
        "status":     p.status,
        "created_at": p.created_at.isoformat(),
    } for p in payments])
