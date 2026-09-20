from flask import Blueprint, request, jsonify, g
from models import db, Project, ProjectMember, Session, User
from utils import account_api_key_required, login_required, project_access
from config import PLAN_LIMITS


projects_bp = Blueprint("projects", __name__, url_prefix="/projects")
plugin_projects_bp = Blueprint("plugin_projects", __name__, url_prefix="/api/plugin")


def project_to_dict(p, member=None):
    return {
        "id": p.id,
        "name": p.name,
        "plan": p.effective_plan,
        "plan_expires_at": p.owner.account_plan_expires_at.isoformat() if p.owner.account_plan_expires_at else None,
        "plan_owner": p.owner.username,
        "created_at": p.created_at.isoformat(),
        "member_count": len(p.members),
        "role": member.role if member else None,
    }


@plugin_projects_bp.route("/projects", methods=["GET"])
@account_api_key_required
def plugin_projects():
    memberships = ProjectMember.query.filter_by(user_id=g.user.id).all()
    return jsonify({
        "username": g.user.username,
        "projects": [{
            "id": membership.project.id,
            "name": membership.project.name,
            "role": membership.role,
            "plan": membership.project.effective_plan,
        } for membership in memberships],
    })


@projects_bp.route("/", methods=["GET"])
@login_required
def list_projects():
    memberships = ProjectMember.query.filter_by(user_id=g.user.id).all()
    return jsonify([project_to_dict(m.project, m) for m in memberships])


@projects_bp.route("/", methods=["POST"])
@login_required
def create_project():
    owned_memberships = ProjectMember.query.filter_by(user_id=g.user.id, role="owner").all()
    owned = len(owned_memberships)
    limit = PLAN_LIMITS[g.user.account_plan]["projects"]
    if limit is not None and owned >= limit:
        return jsonify({"error": f"Your current plan is limited to {limit} owned project(s). Upgrade to create more."}), 403

    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Project name is required"}), 400
    if len(name) > 32:
        return jsonify({"error": "Project name must be 32 characters or fewer"}), 400

    project = Project(owner_id=g.user.id, name=name)
    db.session.add(project)
    db.session.flush()
    db.session.add(ProjectMember(project_id=project.id, user_id=g.user.id, role="owner"))
    db.session.commit()
    owner_member = ProjectMember.query.filter_by(project_id=project.id, user_id=g.user.id).first()
    return jsonify(project_to_dict(project, owner_member)), 201


@projects_bp.route("/<project_id>", methods=["GET"])
@project_access()
def get_project(project_id):
    return jsonify(project_to_dict(g.project, g.member))


@projects_bp.route("/<project_id>", methods=["PATCH"])
@project_access(role_required="owner")
def update_project(project_id):
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Project name is required"}), 400
    if len(name) > 32:
        return jsonify({"error": "Project name must be 32 characters or fewer"}), 400
    g.project.name = name
    db.session.commit()
    return jsonify({"ok": True, "name": name})


@projects_bp.route("/<project_id>/members", methods=["GET"])
@project_access()
def list_members(project_id):
    members = ProjectMember.query.filter_by(project_id=project_id).all()
    sessions_by_user = {}
    for session in Session.query.filter_by(project_id=project_id).order_by(Session.started_at.desc()).all():
        sessions_by_user.setdefault(session.user_id, []).append(session)
    result = []
    for member in members:
        sessions = sessions_by_user.get(member.user_id, [])
        active = any(session.is_live for session in sessions)
        latest = sessions[0] if sessions else None
        last_seen = None if active or not latest else latest.effective_end_at.isoformat()
        result.append({
            "user_id": member.user_id,
            "username": member.user.username,
            "role": member.role,
            "joined_at": member.joined_at.isoformat(),
            "active": active,
            "last_seen": last_seen,
        })
    return jsonify(result)


@projects_bp.route("/<project_id>/members/invite", methods=["POST"])
@project_access(role_required="admin")
def invite_member(project_id):
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    if not username:
        return jsonify({"error": "Username is required"}), 400

    target = User.query.filter_by(username=username).first()
    if not target:
        return jsonify({"error": "User not found"}), 404

    existing = ProjectMember.query.filter_by(project_id=project_id, user_id=target.id).first()
    if existing:
        return jsonify({"error": "That user is already a member"}), 409

    current = ProjectMember.query.filter_by(project_id=project_id).count()
    limit = g.project.max_members
    if limit is not None and current >= limit:
        return jsonify({"error": f"Member limit reached ({limit}). Ask the project owner to upgrade their account plan."}), 403

    db.session.add(ProjectMember(project_id=project_id, user_id=target.id, role="member"))
    db.session.commit()
    return jsonify({"ok": True, "username": target.username, "role": "member"}), 201


@projects_bp.route("/<project_id>/members/<user_id>/role", methods=["PATCH"])
@project_access(role_required="owner")
def set_role(project_id, user_id):
    data = request.get_json(silent=True) or {}
    role = data.get("role")
    if role not in ("co_admin", "member"):
        return jsonify({"error": "Role must be co_admin or member"}), 400

    member = ProjectMember.query.filter_by(project_id=project_id, user_id=user_id).first()
    if not member or member.role == "owner":
        return jsonify({"error": "The owner role cannot be changed"}), 400

    if role == "co_admin":
        limit = g.project.max_co_admins
        current_admins = ProjectMember.query.filter_by(project_id=project_id, role="co_admin").count()
        if limit is not None and current_admins >= limit:
            return jsonify({"error": f"Co-admin limit reached ({limit}). Ask the project owner to upgrade their account plan."}), 403

    member.role = role
    db.session.commit()
    return jsonify({"ok": True, "role": role})


@projects_bp.route("/<project_id>/members/<user_id>", methods=["DELETE"])
@project_access(role_required="admin")
def remove_member(project_id, user_id):
    member = ProjectMember.query.filter_by(project_id=project_id, user_id=user_id).first()
    if not member or member.role == "owner":
        return jsonify({"error": "The owner cannot be removed"}), 400
    from models import Task, TaskAssignment
    task_ids = [task.id for task in Task.query.filter_by(project_id=project_id).all()]
    if task_ids:
        TaskAssignment.query.filter(
            TaskAssignment.task_id.in_(task_ids),
            TaskAssignment.user_id == user_id,
        ).delete(synchronize_session=False)
    db.session.delete(member)
    db.session.commit()
    return jsonify({"ok": True})


@projects_bp.route("/<project_id>", methods=["DELETE"])
@project_access(role_required="owner")
def delete_project(project_id):
    db.session.delete(g.project)
    db.session.commit()
    return jsonify({"ok": True})
