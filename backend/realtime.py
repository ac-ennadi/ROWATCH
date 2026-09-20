from flask import request
from flask_socketio import SocketIO, emit, join_room

from models import ProjectMember, User
from utils import decode_token


socketio = SocketIO(cors_allowed_origins=[], async_mode="threading")


def _socket_user():
    token = request.cookies.get("token")
    if not token:
        return None
    try:
        payload = decode_token(token)
        return User.query.get(payload["sub"])
    except Exception:
        return None


@socketio.on("connect")
def on_connect(auth=None):
    user = _socket_user()
    if not user:
        return False
    emit("ready", {"ok": True, "username": user.username})


@socketio.on("join_project")
def on_join_project(data):
    user = _socket_user()
    project_id = str((data or {}).get("project_id") or "")
    if not user or not project_id:
        emit("project_joined", {"ok": False, "error": "Unauthorized"})
        return
    member = ProjectMember.query.filter_by(
        project_id=project_id, user_id=user.id
    ).first()
    if not member:
        emit("project_joined", {"ok": False, "error": "Access denied"})
        return
    join_room(f"project:{project_id}")
    emit("project_joined", {"ok": True, "project_id": project_id})


def publish_project_update(project_id, event_type, payload=None):
    socketio.emit(
        "project_update",
        {"project_id": project_id, "type": event_type, **(payload or {})},
        to=f"project:{project_id}",
    )
