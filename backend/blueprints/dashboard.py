from flask import Blueprint, Response, jsonify, g, request
import csv
import io
from models import db, Session, ScriptEvent, InstanceEvent, ProjectMember, User
from utils import login_required, project_access
from datetime import datetime, timedelta
from sqlalchemy import func, literal
from config import PLAN_LIMITS

dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")

def session_stats(sessions):
    total_sec = sum(s.duration_seconds for s in sessions)
    script_events = []
    instance_events = []
    for session in sessions:
        script_events.extend(session.script_events)
        instance_events.extend(session.instance_events)

    def instance_total(category, action):
        return sum(
            event.count for event in instance_events
            if event.category == category and event.action == action
        )

    return {
        "total_sessions": len(sessions),
        "total_seconds": total_sec,
        "chars_added": sum(event.chars_added for event in script_events),
        "chars_removed": sum(event.chars_removed for event in script_events),
        "scripts_opened": sum(1 for event in script_events if event.event_type == "open"),
        "parts_added": instance_total("part", "added"),
        "parts_removed": instance_total("part", "removed"),
        "ui_added": instance_total("ui", "added"),
        "ui_removed": instance_total("ui", "removed"),
    }


def sessions_to_list(sessions):
    result = []
    for session in sessions:
        events = [{
            "id": event.id,
            "script": event.script_name,
            "event_type": event.event_type,
            "chars_added": event.chars_added,
            "chars_removed": event.chars_removed,
            "occurred_at": event.occurred_at.isoformat(),
        } for event in sorted(session.script_events, key=lambda item: item.occurred_at)]

        instance_events = [{
            "id": event.id,
            "category": event.category,
            "action": event.action,
            "class_name": event.class_name,
            "instance_name": event.instance_name,
            "count": event.count,
            "occurred_at": event.occurred_at.isoformat(),
        } for event in sorted(session.instance_events, key=lambda item: item.occurred_at)]

        result.append({
            "id": session.id,
            "user": session.user.username,
            "started_at": session.started_at.isoformat(),
            "ended_at": session.ended_at.isoformat() if session.ended_at else None,
            "duration_sec": session.duration_seconds,
            "active": session.is_live,
            "events": events,
            "instance_events": instance_events,
        })
    return result


# ── Member: own stats ───────────────────────────────────────

@dashboard_bp.route("/<project_id>/me", methods=["GET"])
@project_access()
def my_stats(project_id):
    sessions = Session.query.filter_by(
        project_id=project_id,
        user_id=g.user.id
    ).order_by(Session.started_at.desc()).all()

    return jsonify({
        "username": g.user.username,
        "stats":    session_stats(sessions),
        "sessions": sessions_to_list(sessions),
    })

# ── Admin: full project dashboard ───────────────────────────

@dashboard_bp.route("/<project_id>/overview", methods=["GET"])
@project_access(role_required="admin")
def project_overview(project_id):
    members = ProjectMember.query.filter_by(project_id=project_id).all()
    result  = []

    for m in members:
        sessions = Session.query.filter_by(
            project_id=project_id,
            user_id=m.user_id
        ).all()
        active = any(session.is_live for session in sessions)
        latest = max(sessions, key=lambda session: session.started_at) if sessions else None
        result.append({
            "user_id":  m.user_id,
            "username": m.user.username,
            "role":     m.role,
            "stats":    session_stats(sessions),
            "active":   active,
            "last_seen": None if active or not latest else latest.effective_end_at.isoformat(),
        })

    return jsonify({
        "project":  g.project.name,
        "plan":     g.project.effective_plan,
        "members":  result,
    })

@dashboard_bp.route("/<project_id>/members/<user_id>/stats", methods=["GET"])
@project_access(role_required="admin")
def member_stats(project_id, user_id):
    sessions = Session.query.filter_by(
        project_id=project_id,
        user_id=user_id
    ).order_by(Session.started_at.desc()).all()

    if not sessions and not ProjectMember.query.filter_by(
        project_id=project_id, user_id=user_id
    ).first():
        return jsonify({"error": "Member not found"}), 404

    member = ProjectMember.query.filter_by(
        project_id=project_id, user_id=user_id
    ).first()

    return jsonify({
        "username": member.user.username if member else user_id,
        "stats":    session_stats(sessions),
        "sessions": sessions_to_list(sessions),
    })

@dashboard_bp.route("/<project_id>/activity", methods=["GET"])
@project_access()
def full_activity(project_id):
    """Paginated project activity with parameterized, literal server-side search."""
    try:
        page = int(request.args.get("page", "1"))
    except (TypeError, ValueError):
        return jsonify({"error": "page must be a positive integer"}), 400
    if page < 1 or page > 1_000_000:
        return jsonify({"error": "page must be a positive integer"}), 400
    page_size = 200
    search = (request.args.get("q") or "").strip()[:100]
    member = (request.args.get("member") or "").strip()[:64]

    script_query = db.session.query(
        User.username.label("username"), Session.id.label("session_id"),
        ScriptEvent.script_name.label("script"), ScriptEvent.event_type.label("event_type"),
        ScriptEvent.chars_added.label("chars_added"), ScriptEvent.chars_removed.label("chars_removed"),
        literal(None).label("count"), literal(None).label("class_name"),
        ScriptEvent.occurred_at.label("occurred_at"),
    ).join(Session, ScriptEvent.session_id == Session.id).join(User, Session.user_id == User.id).filter(Session.project_id == project_id)
    instance_query = db.session.query(
        User.username.label("username"), Session.id.label("session_id"),
        InstanceEvent.instance_name.label("script"),
        (InstanceEvent.category + literal("_") + InstanceEvent.action).label("event_type"),
        literal(0).label("chars_added"), literal(0).label("chars_removed"),
        InstanceEvent.count.label("count"), InstanceEvent.class_name.label("class_name"),
        InstanceEvent.occurred_at.label("occurred_at"),
    ).join(Session, InstanceEvent.session_id == Session.id).join(User, Session.user_id == User.id).filter(Session.project_id == project_id)

    if g.member.role not in ("owner", "co_admin"):
        script_query = script_query.filter(Session.user_id == g.user.id)
        instance_query = instance_query.filter(Session.user_id == g.user.id)
    elif member:
        script_query = script_query.filter(User.username == member)
        instance_query = instance_query.filter(User.username == member)

    activity = script_query.union_all(instance_query).subquery()
    query = db.session.query(activity)
    if search:
        # Escape LIKE metacharacters so input is treated literally; SQLAlchemy binds the value.
        escaped = search.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        query = query.filter(db.or_(
            func.lower(activity.c.username).like(pattern, escape="\\"),
            func.lower(activity.c.script).like(pattern, escape="\\"),
            func.lower(activity.c.event_type).like(pattern, escape="\\"),
            func.lower(func.coalesce(activity.c.class_name, "")).like(pattern, escape="\\"),
        ))

    total = query.count()
    rows = query.order_by(activity.c.occurred_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    items = []
    for row in rows:
        item = dict(row._mapping)
        item["occurred_at"] = item["occurred_at"].isoformat()
        items.append(item)
    return jsonify({
        "items": items, "page": page, "page_size": page_size, "total": total,
        "pages": max(1, (total + page_size - 1) // page_size),
    })

# ── Charts data ──────────────────────────────────────────────

@dashboard_bp.route("/<project_id>/export.csv", methods=["GET"])
@project_access(role_required="admin")
def export_activity(project_id):
    """Export retained project activity for paid plans."""
    if not PLAN_LIMITS[g.project.effective_plan]["export"]:
        return jsonify({
            "error": "CSV export requires a Pro or Studio account plan.",
            "upgrade_required": True,
        }), 403

    def safe_cell(value):
        text_value = str(value or "")
        if text_value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
            return "'" + text_value
        return text_value
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "username", "session_id", "event_type", "name", "class_name",
        "chars_added", "chars_removed", "count", "occurred_at",
    ])
    sessions = Session.query.filter_by(project_id=project_id).order_by(Session.started_at.asc()).all()
    for session in sessions:
        for event in sorted(session.script_events, key=lambda item: item.occurred_at):
            writer.writerow([
                safe_cell(session.user.username), session.id, event.event_type, safe_cell(event.script_name), "",
                event.chars_added, event.chars_removed, "", event.occurred_at.isoformat(),
            ])
        for event in sorted(session.instance_events, key=lambda item: item.occurred_at):
            writer.writerow([
                safe_cell(session.user.username), session.id, f"{event.category}_{event.action}",
                safe_cell(event.instance_name), safe_cell(event.class_name), "", "", event.count,
                event.occurred_at.isoformat(),
            ])
    filename = f"rowatch-{g.project.name[:48].strip() or 'project'}-activity.csv"
    safe_filename = "".join(character if character.isalnum() or character in "-_." else "-" for character in filename)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{safe_filename}"'},
    )


@dashboard_bp.route("/<project_id>/charts/daily", methods=["GET"])
@project_access(role_required="admin")
def daily_charts(project_id):
    """Sessions per day for the last 30 days."""
    cutoff   = datetime.utcnow() - timedelta(days=30)
    sessions = Session.query.filter(
        Session.project_id == project_id,
        Session.started_at >= cutoff
    ).all()

    by_day = {}
    for s in sessions:
        day = s.started_at.strftime("%Y-%m-%d")
        if day not in by_day:
            by_day[day] = {"sessions": 0, "seconds": 0, "chars_added": 0}
        by_day[day]["sessions"] += 1
        by_day[day]["seconds"]  += s.duration_seconds
        for e in s.script_events:
            by_day[day]["chars_added"] += e.chars_added

    return jsonify(by_day)
