from datetime import datetime

from flask import Blueprint, g, jsonify, request

from models import db, ProjectDocument, ProjectMember, Task, TaskAssignment
from realtime import publish_project_update
from utils import plugin_auth, project_access


workspace_bp = Blueprint("workspace", __name__, url_prefix="/workspace")
plugin_tasks_bp = Blueprint("plugin_tasks", __name__, url_prefix="/api/tasks")


def _is_admin():
    return g.member.role in ("owner", "co_admin")


def _require_admin():
    if not _is_admin():
        return jsonify({"error": "Admin required"}), 403
    return None


def _parse_due(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        raise ValueError("Invalid due date")


def _task_dict(task, current_user_id):
    assignments = [{
        "user_id": item.user_id,
        "username": item.user.username,
        "completed": item.completed,
        "completed_at": item.completed_at.isoformat() if item.completed_at else None,
    } for item in task.assignments]
    mine = next((item for item in assignments if item["user_id"] == current_user_id), None)
    return {
        "id": task.id,
        "title": task.title,
        "description_md": task.description_md or "",
        "due_at": task.due_at.isoformat() if task.due_at else None,
        "created_by": task.created_by.username,
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
        "assignments": assignments,
        "assigned_to_me": mine is not None,
        "my_completed": mine["completed"] if mine else False,
        "completed_count": sum(1 for item in assignments if item["completed"]),
    }


def _document_dict(document):
    return {
        "id": document.id,
        "title": document.title,
        "content_md": document.content_md or "",
        "created_by": document.created_by.username,
        "created_at": document.created_at.isoformat(),
        "updated_at": document.updated_at.isoformat(),
    }


def _valid_assignees(project_id, user_ids):
    requested = list(dict.fromkeys(str(item) for item in (user_ids or []) if item))
    if not requested:
        return []
    members = ProjectMember.query.filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id.in_(requested),
    ).all()
    if len(members) != len(requested):
        raise ValueError("Every assignee must be a project member")
    return members


@workspace_bp.route("/<project_id>/tasks", methods=["GET"])
@project_access()
def list_tasks(project_id):
    tasks = Task.query.filter_by(project_id=project_id).order_by(Task.created_at.desc()).all()
    return jsonify([_task_dict(task, g.user.id) for task in tasks])


@workspace_bp.route("/<project_id>/tasks", methods=["POST"])
@project_access()
def create_task(project_id):
    denied = _require_admin()
    if denied:
        return denied
    data = request.get_json(silent=True) or {}
    title = str(data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "Task title is required"}), 400
    try:
        members = _valid_assignees(project_id, data.get("assignee_ids"))
        due_at = _parse_due(data.get("due_at"))
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    task = Task(
        project_id=project_id,
        created_by_id=g.user.id,
        title=title[:200],
        description_md=str(data.get("description_md") or ""),
        due_at=due_at,
    )
    db.session.add(task)
    db.session.flush()
    for member in members:
        db.session.add(TaskAssignment(task_id=task.id, user_id=member.user_id))
    db.session.commit()
    publish_project_update(project_id, "task_updated", {"task_id": task.id})
    return jsonify(_task_dict(task, g.user.id)), 201


@workspace_bp.route("/<project_id>/tasks/<task_id>", methods=["PATCH"])
@project_access()
def update_task(project_id, task_id):
    denied = _require_admin()
    if denied:
        return denied
    task = Task.query.filter_by(id=task_id, project_id=project_id).first()
    if not task:
        return jsonify({"error": "Task not found"}), 404
    data = request.get_json(silent=True) or {}
    if "title" in data:
        title = str(data.get("title") or "").strip()
        if not title:
            return jsonify({"error": "Task title is required"}), 400
        task.title = title[:200]
    if "description_md" in data:
        task.description_md = str(data.get("description_md") or "")
    if "due_at" in data:
        try:
            task.due_at = _parse_due(data.get("due_at"))
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
    if "assignee_ids" in data:
        try:
            members = _valid_assignees(project_id, data.get("assignee_ids"))
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
        previous = {item.user_id: item for item in task.assignments}
        task.assignments.clear()
        db.session.flush()
        for member in members:
            old = previous.get(member.user_id)
            db.session.add(TaskAssignment(
                task_id=task.id,
                user_id=member.user_id,
                completed=old.completed if old else False,
                completed_at=old.completed_at if old else None,
            ))
    task.updated_at = datetime.utcnow()
    db.session.commit()
    publish_project_update(project_id, "task_updated", {"task_id": task.id})
    return jsonify(_task_dict(task, g.user.id))


@workspace_bp.route("/<project_id>/tasks/<task_id>", methods=["DELETE"])
@project_access()
def delete_task(project_id, task_id):
    denied = _require_admin()
    if denied:
        return denied
    task = Task.query.filter_by(id=task_id, project_id=project_id).first()
    if not task:
        return jsonify({"error": "Task not found"}), 404
    db.session.delete(task)
    db.session.commit()
    publish_project_update(project_id, "task_updated", {"task_id": task_id})
    return jsonify({"ok": True})


def _toggle(task, user_id, completed):
    assignment = TaskAssignment.query.filter_by(task_id=task.id, user_id=user_id).first()
    if not assignment:
        return None
    assignment.completed = bool(completed)
    assignment.completed_at = datetime.utcnow() if assignment.completed else None
    task.updated_at = datetime.utcnow()
    db.session.commit()
    publish_project_update(task.project_id, "task_updated", {"task_id": task.id})
    return assignment


@workspace_bp.route("/<project_id>/tasks/<task_id>/complete", methods=["POST"])
@project_access()
def complete_task(project_id, task_id):
    task = Task.query.filter_by(id=task_id, project_id=project_id).first()
    if not task:
        return jsonify({"error": "Task not found"}), 404
    data = request.get_json(silent=True) or {}
    assignment = _toggle(task, g.user.id, data.get("completed", True))
    if not assignment:
        return jsonify({"error": "Task is not assigned to you"}), 403
    return jsonify({"ok": True, "completed": assignment.completed})


@workspace_bp.route("/<project_id>/documents", methods=["GET"])
@project_access()
def list_documents(project_id):
    documents = ProjectDocument.query.filter_by(project_id=project_id).order_by(ProjectDocument.updated_at.desc()).all()
    return jsonify([_document_dict(document) for document in documents])


@workspace_bp.route("/<project_id>/documents", methods=["POST"])
@project_access()
def create_document(project_id):
    denied = _require_admin()
    if denied:
        return denied
    data = request.get_json(silent=True) or {}
    title = str(data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "Document title is required"}), 400
    document = ProjectDocument(
        project_id=project_id,
        created_by_id=g.user.id,
        title=title[:200],
        content_md=str(data.get("content_md") or ""),
    )
    db.session.add(document)
    db.session.commit()
    publish_project_update(project_id, "document_updated", {"document_id": document.id})
    return jsonify(_document_dict(document)), 201


@workspace_bp.route("/<project_id>/documents/<document_id>", methods=["PATCH"])
@project_access()
def update_document(project_id, document_id):
    denied = _require_admin()
    if denied:
        return denied
    document = ProjectDocument.query.filter_by(id=document_id, project_id=project_id).first()
    if not document:
        return jsonify({"error": "Document not found"}), 404
    data = request.get_json(silent=True) or {}
    if "title" in data:
        title = str(data.get("title") or "").strip()
        if not title:
            return jsonify({"error": "Document title is required"}), 400
        document.title = title[:200]
    if "content_md" in data:
        document.content_md = str(data.get("content_md") or "")
    document.updated_at = datetime.utcnow()
    db.session.commit()
    publish_project_update(project_id, "document_updated", {"document_id": document.id})
    return jsonify(_document_dict(document))


@workspace_bp.route("/<project_id>/documents/<document_id>", methods=["DELETE"])
@project_access()
def delete_document(project_id, document_id):
    denied = _require_admin()
    if denied:
        return denied
    document = ProjectDocument.query.filter_by(id=document_id, project_id=project_id).first()
    if not document:
        return jsonify({"error": "Document not found"}), 404
    db.session.delete(document)
    db.session.commit()
    publish_project_update(project_id, "document_updated", {"document_id": document_id})
    return jsonify({"ok": True})


@plugin_tasks_bp.route("", methods=["GET"])
@plugin_auth
def plugin_list_tasks():
    assignments = TaskAssignment.query.join(Task).filter(
        Task.project_id == g.project.id,
        TaskAssignment.user_id == g.user.id,
    ).all()
    tasks = sorted((item.task for item in assignments), key=lambda task: (task.due_at is None, task.due_at or task.created_at))
    return jsonify([_task_dict(task, g.user.id) for task in tasks])


@plugin_tasks_bp.route("/<task_id>/complete", methods=["POST"])
@plugin_auth
def plugin_complete_task(task_id):
    task = Task.query.filter_by(id=task_id, project_id=g.project.id).first()
    if not task:
        return jsonify({"error": "Task not found"}), 404
    data = request.get_json(silent=True) or {}
    assignment = _toggle(task, g.user.id, data.get("completed", True))
    if not assignment:
        return jsonify({"error": "Task is not assigned to you"}), 403
    return jsonify({"ok": True, "completed": assignment.completed})
