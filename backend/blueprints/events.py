from flask import Blueprint, request, jsonify, g
from models import db, Session, ScriptEvent, InstanceEvent
from utils import plugin_auth
from realtime import publish_project_update
from datetime import datetime

events_bp = Blueprint("events", __name__, url_prefix="/api/events")

@events_bp.route("/session/start", methods=["POST"])
@plugin_auth
def session_start():
    # Close any open session for this user in this project
    open_session = Session.query.filter_by(
        project_id=g.project.id,
        user_id=g.user.id,
        ended_at=None
    ).first()
    if open_session:
        open_session.ended_at = datetime.utcnow()

    session = Session(project_id=g.project.id, user_id=g.user.id)
    db.session.add(session)
    db.session.commit()
    publish_project_update(g.project.id, "session_started", {"username": g.user.username})

    return jsonify({"session_id": session.id, "started_at": session.started_at.isoformat()})

@events_bp.route("/session/end", methods=["POST"])
@plugin_auth
def session_end():
    data       = request.get_json(silent=True) or {}
    session_id = data.get("session_id")

    session = Session.query.filter_by(id=session_id, user_id=g.user.id).first()
    if not session:
        return jsonify({"error": "Session not found"}), 404
    if session.ended_at:
        return jsonify({"error": "Session already ended"}), 400

    session.ended_at = datetime.utcnow()
    db.session.commit()
    publish_project_update(g.project.id, "session_ended", {"username": g.user.username})

    return jsonify({
        "ok":           True,
        "session_id":   session.id,
        "duration_sec": session.duration_seconds,
    })

@events_bp.route("/session/heartbeat", methods=["POST"])
@plugin_auth
def session_heartbeat():
    data = request.get_json(silent=True) or {}
    session = Session.query.filter_by(
        id=data.get("session_id"),
        project_id=g.project.id,
        user_id=g.user.id,
        ended_at=None,
    ).first()
    if not session:
        return jsonify({"error": "Active session not found"}), 404
    publish_project_update(g.project.id, "session_heartbeat", {"username": g.user.username})
    return jsonify({"ok": True, "duration_sec": session.duration_seconds})

@events_bp.route("/script/open", methods=["POST"])
@plugin_auth
def script_open():
    data        = request.get_json(silent=True) or {}
    session_id  = data.get("session_id")
    script_name = (data.get("script") or "").strip()

    if not session_id or not script_name:
        return jsonify({"error": "session_id and script required"}), 400

    session = Session.query.filter_by(id=session_id, user_id=g.user.id, ended_at=None).first()
    if not session:
        return jsonify({"error": "Active session not found"}), 404

    event = ScriptEvent(
        session_id=session_id,
        script_name=script_name,
        event_type="open",
        chars_added=0,
        chars_removed=0,
    )
    db.session.add(event)
    db.session.commit()
    publish_project_update(g.project.id, "script_event", {"username": g.user.username})
    return jsonify({"ok": True, "event_id": event.id})

@events_bp.route("/script/close", methods=["POST"])
@plugin_auth
def script_close():
    data          = request.get_json(silent=True) or {}
    session_id    = data.get("session_id")
    script_name   = (data.get("script") or "").strip()
    chars_added   = int(data.get("chars_added") or 0)
    chars_removed = int(data.get("chars_removed") or 0)
    opened_at     = data.get("opened_at")

    if not session_id or not script_name:
        return jsonify({"error": "session_id and script required"}), 400

    session = Session.query.filter_by(id=session_id, user_id=g.user.id).first()
    if not session:
        return jsonify({"error": "Session not found"}), 404

    event = ScriptEvent(
        session_id=session_id,
        script_name=script_name,
        event_type="close",
        chars_added=max(0, chars_added),
        chars_removed=max(0, chars_removed),
        occurred_at=datetime.utcnow(),
    )
    db.session.add(event)
    db.session.commit()
    publish_project_update(g.project.id, "script_event", {"username": g.user.username})
    return jsonify({"ok": True, "event_id": event.id})

@events_bp.route("/instance/change", methods=["POST"])
@plugin_auth
def instance_change():
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id")
    items = data.get("events") if isinstance(data.get("events"), list) else [data]

    if not session_id:
        return jsonify({"error": "session_id required"}), 400

    session = Session.query.filter_by(
        id=session_id,
        project_id=g.project.id,
        user_id=g.user.id,
        ended_at=None,
    ).first()
    if not session:
        return jsonify({"error": "Active session not found"}), 404

    created = []
    for item in items[:100]:
        category = str(item.get("category") or "").lower()
        action = str(item.get("action") or "").lower()
        if category not in ("part", "ui") or action not in ("added", "removed"):
            continue
        class_name = str(item.get("class_name") or "Unknown")[:64]
        instance_name = str(item.get("instance_name") or class_name)[:256]
        count = min(max(int(item.get("count") or 1), 1), 1000)
        event = InstanceEvent(
            session_id=session.id,
            category=category,
            action=action,
            class_name=class_name,
            instance_name=instance_name,
            count=count,
        )
        db.session.add(event)
        created.append(event)

    if not created:
        return jsonify({"error": "No valid instance events"}), 400
    db.session.commit()
    publish_project_update(g.project.id, "instance_event", {"username": g.user.username})
    return jsonify({"ok": True, "recorded": len(created)})

@events_bp.route("/ping", methods=["GET"])
@plugin_auth
def ping():
    return jsonify({
        "ok":       True,
        "project":  g.project.name,
        "username": g.user.username,
        "plan":     g.project.effective_plan,
    })
