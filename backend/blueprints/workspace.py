from datetime import datetime
import re

from flask import Blueprint, g, jsonify, request

from config import PLAN_LIMITS
from models import db, DocumentLink, ProjectDocument, ProjectMember, Task, TaskAssignment, TaskColumn
from realtime import publish_project_update
from utils import plugin_auth, project_access


workspace_bp = Blueprint("workspace", __name__, url_prefix="/workspace")
plugin_tasks_bp = Blueprint("plugin_tasks", __name__, url_prefix="/api/tasks")
plugin_documents_bp = Blueprint("plugin_documents", __name__, url_prefix="/api/documents")


NAME_MAX_LENGTH = 32
FREE_DOCUMENT_WORD_LIMIT = 1028


def _word_count(value):
    return len(str(value or "").split())


def _document_content_error(content):
    words = _word_count(content)
    if g.project.effective_plan == "free" and words > FREE_DOCUMENT_WORD_LIMIT:
        return jsonify({
            "error": f"Free plan documentation is limited to {FREE_DOCUMENT_WORD_LIMIT:,} words.",
            "word_limit": FREE_DOCUMENT_WORD_LIMIT,
            "word_count": words,
            "upgrade_required": True,
        }), 400
    return None


DEFAULT_TASK_COLUMNS = ("Backlog", "To do", "In progress", "Done")


def _ensure_task_columns(project_id):
    columns = TaskColumn.query.filter_by(project_id=project_id).order_by(TaskColumn.position, TaskColumn.created_at).all()
    if columns:
        return columns
    columns = [TaskColumn(project_id=project_id, name=name, position=index) for index, name in enumerate(DEFAULT_TASK_COLUMNS)]
    db.session.add_all(columns)
    db.session.flush()
    for index, task_item in enumerate(Task.query.filter_by(project_id=project_id, column_id=None).order_by(Task.created_at).all()):
        task_item.column_id = columns[0].id
        task_item.position = index
    db.session.commit()
    return columns


def _column_dict(column):
    return {
        "id": column.id,
        "name": column.name,
        "position": column.position,
        "task_count": Task.query.filter_by(column_id=column.id).count(),
    }


def _column_for_project(project_id, column_id):
    return TaskColumn.query.filter_by(id=column_id, project_id=project_id).first()


def _append_position(column_id):
    maximum = db.session.query(db.func.max(Task.position)).filter(Task.column_id == column_id).scalar()
    return (maximum if maximum is not None else -1) + 1


def _normalize_task_positions(column_id):
    tasks = Task.query.filter_by(column_id=column_id).order_by(Task.position, Task.created_at).all()
    for index, task_item in enumerate(tasks):
        task_item.position = index


def _is_admin():
    return g.member.role in ("owner", "co_admin")


def _require_admin():
    if not _is_admin():
        return jsonify({"error": "Admin required"}), 403
    return None


def _feature_limit(feature):
    return PLAN_LIMITS.get(g.project.effective_plan, PLAN_LIMITS["free"])[feature]


def _limit_error(feature, current):
    limit = _feature_limit(feature)
    if limit is not None and current >= limit:
        label = "task" if feature == "tasks" else "document"
        return jsonify({
            "error": f"Free projects are limited to {limit} {label}s. Upgrade to Pro for unlimited {feature}.",
            "limit": limit,
            "current": current,
            "upgrade_required": True,
        }), 403
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
        "column_id": task.column_id,
        "column_name": task.column.name if task.column else None,
        "position": task.position,
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


WIKI_LINK_PATTERN = re.compile(r"\[\[([^]\n]{1,64})\]\]")


def _wiki_names(content):
    return list(dict.fromkeys(match.strip() for match in WIKI_LINK_PATTERN.findall(content or "") if match.strip()))


def _sync_document_links(document):
    DocumentLink.query.filter_by(source_document_id=document.id).delete(synchronize_session=False)
    titles = {item.title.casefold(): item for item in ProjectDocument.query.filter_by(project_id=document.project_id).all()}
    for name in _wiki_names(document.content_md):
        target = titles.get(name.casefold())
        if target and target.id != document.id:
            db.session.add(DocumentLink(source_document_id=document.id, target_document_id=target.id))


def _rename_wiki_references(project_id, old_title, new_title):
    pattern = re.compile(r"\[\[\s*" + re.escape(old_title) + r"\s*\]\]", re.IGNORECASE)
    for source in ProjectDocument.query.filter_by(project_id=project_id).all():
        updated = pattern.sub(lambda _match: f"[[{new_title}]]", source.content_md or "")
        if updated != (source.content_md or ""):
            source.content_md = updated
            source.updated_by_id = g.user.id
            source.updated_at = datetime.utcnow()


def _sync_project_document_links(project_id):
    for project_document in ProjectDocument.query.filter_by(project_id=project_id).all():
        _sync_document_links(project_document)


def _document_dict(document):
    outgoing = DocumentLink.query.filter_by(source_document_id=document.id).all()
    incoming = DocumentLink.query.filter_by(target_document_id=document.id).all()
    linked = [db.session.get(ProjectDocument, link.target_document_id) for link in outgoing]
    backlinks = [db.session.get(ProjectDocument, link.source_document_id) for link in incoming]
    resolved_names = {item.title.casefold() for item in linked if item}
    return {
        "id": document.id,
        "title": document.title,
        "content_md": document.content_md or "",
        "created_by": document.created_by.username,
        "updated_by": (document.updated_by or document.created_by).username,
        "created_at": document.created_at.isoformat(),
        "updated_at": document.updated_at.isoformat(),
        "links": [{"id": item.id, "title": item.title} for item in linked if item],
        "backlinks": [{"id": item.id, "title": item.title} for item in backlinks if item],
        "unresolved_links": [name for name in _wiki_names(document.content_md) if name.casefold() not in resolved_names],
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


@workspace_bp.route("/<project_id>/task-columns", methods=["GET"])
@project_access()
def list_task_columns(project_id):
    return jsonify([_column_dict(column) for column in _ensure_task_columns(project_id)])


@workspace_bp.route("/<project_id>/task-columns", methods=["POST"])
@project_access()
def create_task_column(project_id):
    denied = _require_admin()
    if denied:
        return denied
    name = str((request.get_json(silent=True) or {}).get("name") or "").strip()
    if not name:
        return jsonify({"error": "Column name is required"}), 400
    if len(name) > NAME_MAX_LENGTH:
        return jsonify({"error": f"Column name must be {NAME_MAX_LENGTH} characters or fewer"}), 400
    _ensure_task_columns(project_id)
    duplicate = TaskColumn.query.filter(
        TaskColumn.project_id == project_id,
        db.func.lower(TaskColumn.name) == name.lower(),
    ).first()
    if duplicate:
        return jsonify({"error": "A column with this name already exists"}), 409
    position = TaskColumn.query.filter_by(project_id=project_id).count()
    column = TaskColumn(project_id=project_id, name=name, position=position)
    db.session.add(column)
    db.session.commit()
    publish_project_update(project_id, "task_board_updated", {"column_id": column.id})
    return jsonify(_column_dict(column)), 201


@workspace_bp.route("/<project_id>/task-columns/<column_id>", methods=["PATCH"])
@project_access()
def update_task_column(project_id, column_id):
    denied = _require_admin()
    if denied:
        return denied
    column = _column_for_project(project_id, column_id)
    if not column:
        return jsonify({"error": "Task column not found"}), 404
    name = str((request.get_json(silent=True) or {}).get("name") or "").strip()
    if not name:
        return jsonify({"error": "Column name is required"}), 400
    if len(name) > NAME_MAX_LENGTH:
        return jsonify({"error": f"Column name must be {NAME_MAX_LENGTH} characters or fewer"}), 400
    duplicate = TaskColumn.query.filter(
        TaskColumn.project_id == project_id,
        TaskColumn.id != column.id,
        db.func.lower(TaskColumn.name) == name.lower(),
    ).first()
    if duplicate:
        return jsonify({"error": "A column with this name already exists"}), 409
    column.name = name
    column.updated_at = datetime.utcnow()
    db.session.commit()
    publish_project_update(project_id, "task_board_updated", {"column_id": column.id})
    return jsonify(_column_dict(column))


@workspace_bp.route("/<project_id>/task-columns/reorder", methods=["PUT"])
@project_access()
def reorder_task_columns(project_id):
    denied = _require_admin()
    if denied:
        return denied
    columns = _ensure_task_columns(project_id)
    column_ids = [str(value) for value in ((request.get_json(silent=True) or {}).get("column_ids") or [])]
    existing = {column.id: column for column in columns}
    if len(column_ids) != len(existing) or len(set(column_ids)) != len(existing) or set(column_ids) != set(existing):
        return jsonify({"error": "column_ids must contain every project column exactly once"}), 400
    for position, column_id in enumerate(column_ids):
        existing[column_id].position = position
    db.session.commit()
    publish_project_update(project_id, "task_board_updated", {})
    return jsonify([_column_dict(existing[column_id]) for column_id in column_ids])


@workspace_bp.route("/<project_id>/task-columns/<column_id>", methods=["DELETE"])
@project_access()
def delete_task_column(project_id, column_id):
    denied = _require_admin()
    if denied:
        return denied
    columns = _ensure_task_columns(project_id)
    column = next((item for item in columns if item.id == column_id), None)
    if not column:
        return jsonify({"error": "Task column not found"}), 404
    if len(columns) == 1:
        return jsonify({"error": "A task board must keep at least one column"}), 400
    data = request.get_json(silent=True) or {}
    tasks = Task.query.filter_by(column_id=column.id).order_by(Task.position, Task.created_at).all()
    destination = None
    if tasks:
        destination = _column_for_project(project_id, data.get("destination_column_id"))
        if not destination or destination.id == column.id:
            return jsonify({
                "error": "Choose another column for these tasks before deleting this column.",
                "task_count": len(tasks),
                "destination_required": True,
            }), 409
        next_position = _append_position(destination.id)
        for offset, task_item in enumerate(tasks):
            task_item.column_id = destination.id
            task_item.position = next_position + offset
        # Persist the reassignment before SQLAlchemy processes deletion of the old relationship.
        db.session.flush()
    db.session.delete(column)
    remaining = [item for item in columns if item.id != column.id]
    for position, item in enumerate(remaining):
        item.position = position
    db.session.commit()
    publish_project_update(project_id, "task_board_updated", {"deleted_column_id": column.id})
    return jsonify({"ok": True, "moved_tasks": len(tasks), "destination_column_id": destination.id if destination else None})


@workspace_bp.route("/<project_id>/tasks/<task_id>/move", methods=["POST"])
@project_access()
def move_task(project_id, task_id):
    denied = _require_admin()
    if denied:
        return denied
    task_item = Task.query.filter_by(id=task_id, project_id=project_id).first()
    if not task_item:
        return jsonify({"error": "Task not found"}), 404
    data = request.get_json(silent=True) or {}
    destination = _column_for_project(project_id, data.get("column_id"))
    if not destination:
        return jsonify({"error": "Task column not found"}), 400
    try:
        requested_position = int(data.get("position", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "position must be a whole number"}), 400
    source_column_id = task_item.column_id
    if source_column_id == destination.id:
        ordered = [item for item in Task.query.filter_by(column_id=destination.id).order_by(Task.position, Task.created_at).all() if item.id != task_item.id]
    else:
        ordered = Task.query.filter_by(column_id=destination.id).order_by(Task.position, Task.created_at).all()
    target_position = max(0, min(requested_position, len(ordered)))
    ordered.insert(target_position, task_item)
    task_item.column_id = destination.id
    for position, item in enumerate(ordered):
        item.position = position
    if source_column_id and source_column_id != destination.id:
        _normalize_task_positions(source_column_id)
    task_item.updated_at = datetime.utcnow()
    db.session.commit()
    publish_project_update(project_id, "task_updated", {"task_id": task_item.id})
    return jsonify(_task_dict(task_item, g.user.id))


@workspace_bp.route("/<project_id>/tasks", methods=["GET"])
@project_access()
def list_tasks(project_id):
    columns = _ensure_task_columns(project_id)
    tasks = Task.query.filter_by(project_id=project_id).order_by(Task.column_id, Task.position, Task.created_at).all()
    return jsonify({
        "items": [_task_dict(task, g.user.id) for task in tasks],
        "columns": [_column_dict(column) for column in columns],
        "usage": {"current": len(tasks), "limit": _feature_limit("tasks"), "plan": g.project.effective_plan},
    })


@workspace_bp.route("/<project_id>/tasks", methods=["POST"])
@project_access()
def create_task(project_id):
    denied = _require_admin()
    if denied:
        return denied
    current = Task.query.filter_by(project_id=project_id).count()
    limited = _limit_error("tasks", current)
    if limited:
        return limited
    data = request.get_json(silent=True) or {}
    title = str(data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "Task title is required"}), 400
    if len(title) > NAME_MAX_LENGTH:
        return jsonify({"error": f"Task title must be {NAME_MAX_LENGTH} characters or fewer"}), 400
    try:
        members = _valid_assignees(project_id, data.get("assignee_ids"))
        due_at = _parse_due(data.get("due_at"))
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    columns = _ensure_task_columns(project_id)
    column = _column_for_project(project_id, data.get("column_id")) if data.get("column_id") else columns[0]
    if not column:
        return jsonify({"error": "Task column not found"}), 400
    task = Task(
        project_id=project_id,
        created_by_id=g.user.id,
        column_id=column.id,
        position=_append_position(column.id),
        title=title,
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
        if len(title) > NAME_MAX_LENGTH:
            return jsonify({"error": f"Task title must be {NAME_MAX_LENGTH} characters or fewer"}), 400
        task.title = title
    if "column_id" in data and data.get("column_id") != task.column_id:
        column = _column_for_project(project_id, data.get("column_id"))
        if not column:
            return jsonify({"error": "Task column not found"}), 400
        previous_column_id = task.column_id
        task.column_id = column.id
        task.position = _append_position(column.id)
        if previous_column_id:
            _normalize_task_positions(previous_column_id)
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


@workspace_bp.route("/<project_id>/documents/graph", methods=["GET"])
@project_access()
def document_graph(project_id):
    documents = ProjectDocument.query.filter_by(project_id=project_id).order_by(ProjectDocument.title).all()
    document_ids = {document.id for document in documents}
    links = DocumentLink.query.filter(DocumentLink.source_document_id.in_(document_ids)).all() if document_ids else []
    return jsonify({
        "nodes": [{"id": document.id, "title": document.title, "updated_at": document.updated_at.isoformat()} for document in documents],
        "links": [{"source": link.source_document_id, "target": link.target_document_id} for link in links if link.target_document_id in document_ids],
    })


@workspace_bp.route("/<project_id>/documents", methods=["GET"])
@project_access()
def list_documents(project_id):
    documents = ProjectDocument.query.filter_by(project_id=project_id).order_by(ProjectDocument.updated_at.desc()).all()
    return jsonify({
        "items": [_document_dict(document) for document in documents],
        "usage": {"current": len(documents), "limit": _feature_limit("documents"), "plan": g.project.effective_plan},
    })


@workspace_bp.route("/<project_id>/documents", methods=["POST"])
@project_access()
def create_document(project_id):
    denied = _require_admin()
    if denied:
        return denied
    current = ProjectDocument.query.filter_by(project_id=project_id).count()
    limited = _limit_error("documents", current)
    if limited:
        return limited
    data = request.get_json(silent=True) or {}
    title = str(data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "Document title is required"}), 400
    if len(title) > NAME_MAX_LENGTH:
        return jsonify({"error": f"Document title must be {NAME_MAX_LENGTH} characters or fewer"}), 400
    duplicate = ProjectDocument.query.filter(ProjectDocument.project_id == project_id, db.func.lower(ProjectDocument.title) == title.lower()).first()
    if duplicate:
        return jsonify({"error": "A document with this title already exists"}), 409
    content = str(data.get("content_md") or "")
    content_error = _document_content_error(content)
    if content_error:
        return content_error
    document = ProjectDocument(
        project_id=project_id,
        created_by_id=g.user.id,
        updated_by_id=g.user.id,
        title=title,
        content_md=content,
    )
    db.session.add(document)
    db.session.flush()
    _sync_project_document_links(project_id)
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
        if len(title) > NAME_MAX_LENGTH:
            return jsonify({"error": f"Document title must be {NAME_MAX_LENGTH} characters or fewer"}), 400
        duplicate = ProjectDocument.query.filter(ProjectDocument.project_id == project_id, ProjectDocument.id != document.id, db.func.lower(ProjectDocument.title) == title.lower()).first()
        if duplicate:
            return jsonify({"error": "A document with this title already exists"}), 409
        if title != document.title:
            _rename_wiki_references(project_id, document.title, title)
        document.title = title
    if "content_md" in data:
        content = str(data.get("content_md") or "")
        content_error = _document_content_error(content)
        if content_error:
            return content_error
        document.content_md = content
    document.updated_by_id = g.user.id
    document.updated_at = datetime.utcnow()
    db.session.flush()
    _sync_project_document_links(project_id)
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
    DocumentLink.query.filter(db.or_(DocumentLink.source_document_id == document.id, DocumentLink.target_document_id == document.id)).delete(synchronize_session=False)
    db.session.delete(document)
    db.session.commit()
    publish_project_update(project_id, "document_updated", {"document_id": document_id})
    return jsonify({"ok": True})


@plugin_documents_bp.route("", methods=["GET"])
@plugin_auth
def plugin_list_documents():
    documents = ProjectDocument.query.filter_by(project_id=g.project.id).order_by(ProjectDocument.updated_at.desc()).all()
    return jsonify([_document_dict(document) for document in documents])


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
