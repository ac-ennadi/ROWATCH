from flask import Blueprint, Response, jsonify, g
import csv
import io
from models import Session, ScriptEvent, InstanceEvent, ProjectMember
from utils import login_required, project_access
from datetime import datetime, timedelta
from sqlalchemy import func
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
            "active": session.ended_at is None,
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
        result.append({
            "user_id":  m.user_id,
            "username": m.user.username,
            "role":     m.role,
            "stats":    session_stats(sessions),
            "active":   any(s.ended_at is None for s in sessions),
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
@project_access(role_required="admin")
def full_activity(project_id):
    """All script events across all members, newest first."""
    sessions = Session.query.filter_by(project_id=project_id).all()
    all_events = []
    for s in sessions:
        for e in s.script_events:
            all_events.append({
                "username":     s.user.username,
                "session_id":   s.id,
                "script":       e.script_name,
                "event_type":   e.event_type,
                "chars_added":  e.chars_added,
                "chars_removed":e.chars_removed,
                "occurred_at":  e.occurred_at.isoformat(),
            })
        for e in s.instance_events:
            all_events.append({
                "username": s.user.username,
                "session_id": s.id,
                "script": e.instance_name,
                "event_type": f"{e.category}_{e.action}",
                "chars_added": 0,
                "chars_removed": 0,
                "count": e.count,
                "class_name": e.class_name,
                "occurred_at": e.occurred_at.isoformat(),
            })
    all_events.sort(key=lambda x: x["occurred_at"], reverse=True)
    return jsonify(all_events)

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
