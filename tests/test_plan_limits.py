from datetime import datetime, timedelta

from config import PLAN_LIMITS
from conftest import register
from models import ProjectMember, Session, User, db
from utils import purge_old_data


def seed_users(app, prefix, count):
    with app.app_context():
        users = []
        for index in range(count):
            user = User(
                username=f"{prefix}{index}",
                email=f"{prefix.lower()}{index}@example.test",
                password_hash="unused-in-plan-tests",
            )
            db.session.add(user)
            users.append(user)
        db.session.commit()
        return [(user.id, user.username) for user in users]


def create_tasks(client, project_id, count):
    return [
        client.post(f"/workspace/{project_id}/tasks", json={"title": f"Task {index}"})
        for index in range(count)
    ]


def create_documents(client, project_id, count):
    return [
        client.post(f"/workspace/{project_id}/documents", json={"title": f"Document {index}"})
        for index in range(count)
    ]


def test_published_plan_matrix_is_stable(client):
    response = client.get("/payments/plans")
    assert response.status_code == 200
    plans = response.get_json()
    expected = {
        "free": {"projects": 1, "members": 5, "history_days": 7, "co_admins": 0, "export": False, "tasks": 10, "documents": 3},
        "pro": {"projects": 3, "members": 15, "history_days": 60, "co_admins": 1, "export": True, "tasks": None, "documents": None},
        "studio": {"projects": None, "members": None, "history_days": None, "co_admins": None, "export": True, "tasks": None, "documents": None},
    }
    for name, limits in expected.items():
        for feature, value in limits.items():
            assert plans[name][feature] == value
            assert PLAN_LIMITS[name][feature] == value


def test_free_plan_enforces_every_resource_limit(app, registered_client):
    project = registered_client.post("/projects/", json={"name": "Free limits"}).get_json()
    assert registered_client.post("/projects/", json={"name": "Second project"}).status_code == 403

    task_responses = create_tasks(registered_client, project["id"], 11)
    assert [response.status_code for response in task_responses[:10]] == [201] * 10
    assert task_responses[10].status_code == 403
    task_usage = registered_client.get(f"/workspace/{project['id']}/tasks").get_json()["usage"]
    assert task_usage == {"current": 10, "limit": 10, "plan": "free"}

    document_responses = create_documents(registered_client, project["id"], 4)
    assert [response.status_code for response in document_responses[:3]] == [201] * 3
    assert document_responses[3].status_code == 403

    invitees = seed_users(app, "FreeMember", 5)
    for _, username in invitees[:4]:
        assert registered_client.post(f"/projects/{project['id']}/members/invite", json={"username": username}).status_code == 201
    assert registered_client.post(
        f"/projects/{project['id']}/members/invite", json={"username": invitees[4][1]}
    ).status_code == 403
    assert registered_client.patch(
        f"/projects/{project['id']}/members/{invitees[0][0]}/role", json={"role": "co_admin"}
    ).status_code == 403
    export = registered_client.get(f"/dashboard/{project['id']}/export.csv")
    assert export.status_code == 403
    assert export.get_json()["upgrade_required"] is True


def test_pro_plan_enforces_projects_members_and_coadmins_but_not_workspace_limits(app, issue_code):
    owner = app.test_client()
    assert register(owner, "ProOwner").status_code == 201
    assert owner.post("/payments/codes/redeem", json={"code": issue_code("pro", 30)}).status_code == 200

    projects = [owner.post("/projects/", json={"name": f"Pro {index}"}) for index in range(4)]
    assert [response.status_code for response in projects] == [201, 201, 201, 403]
    project_id = projects[0].get_json()["id"]

    invitees = seed_users(app, "ProMember", 15)
    for _, username in invitees[:14]:
        assert owner.post(f"/projects/{project_id}/members/invite", json={"username": username}).status_code == 201
    assert owner.post(f"/projects/{project_id}/members/invite", json={"username": invitees[14][1]}).status_code == 403

    assert owner.patch(
        f"/projects/{project_id}/members/{invitees[0][0]}/role", json={"role": "co_admin"}
    ).status_code == 200
    assert owner.patch(
        f"/projects/{project_id}/members/{invitees[1][0]}/role", json={"role": "co_admin"}
    ).status_code == 403

    assert all(response.status_code == 201 for response in create_tasks(owner, project_id, 11))
    assert all(response.status_code == 201 for response in create_documents(owner, project_id, 4))
    export = owner.get(f"/dashboard/{project_id}/export.csv")
    assert export.status_code == 200
    assert export.mimetype == "text/csv"
    assert export.get_data(as_text=True).startswith("username,session_id,event_type")


def test_studio_plan_is_unlimited_for_all_counted_resources(app, issue_code):
    owner = app.test_client()
    assert register(owner, "StudioOwner").status_code == 201
    assert owner.post("/payments/codes/redeem", json={"code": issue_code("studio", 30)}).status_code == 200

    projects = [owner.post("/projects/", json={"name": f"Studio {index}"}) for index in range(4)]
    assert all(response.status_code == 201 for response in projects)
    project_id = projects[0].get_json()["id"]

    invitees = seed_users(app, "StudioMember", 16)
    for _, username in invitees:
        assert owner.post(f"/projects/{project_id}/members/invite", json={"username": username}).status_code == 201
    for user_id, _ in invitees[:2]:
        assert owner.patch(
            f"/projects/{project_id}/members/{user_id}/role", json={"role": "co_admin"}
        ).status_code == 200

    assert all(response.status_code == 201 for response in create_tasks(owner, project_id, 11))
    assert all(response.status_code == 201 for response in create_documents(owner, project_id, 4))
    assert owner.get(f"/workspace/{project_id}/tasks").get_json()["usage"]["limit"] is None
    assert owner.get(f"/workspace/{project_id}/documents").get_json()["usage"]["limit"] is None
    assert owner.get(f"/dashboard/{project_id}/export.csv").status_code == 200


def test_history_retention_matches_each_owner_plan(app, issue_code):
    free = app.test_client()
    pro = app.test_client()
    studio = app.test_client()
    assert register(free, "HistoryFree").status_code == 201
    assert register(pro, "HistoryPro").status_code == 201
    assert register(studio, "HistoryStudio").status_code == 201
    assert pro.post("/payments/codes/redeem", json={"code": issue_code("pro", 30)}).status_code == 200
    assert studio.post("/payments/codes/redeem", json={"code": issue_code("studio", 30)}).status_code == 200

    clients = {"free": free, "pro": pro, "studio": studio}
    projects = {
        plan: client.post("/projects/", json={"name": f"{plan} history"}).get_json()
        for plan, client in clients.items()
    }
    with app.app_context():
        user_ids = {user.username: user.id for user in User.query.all()}
        sessions = {
            "free_old": Session(project_id=projects["free"]["id"], user_id=user_ids["HistoryFree"], started_at=datetime.utcnow() - timedelta(days=8)),
            "free_recent": Session(project_id=projects["free"]["id"], user_id=user_ids["HistoryFree"], started_at=datetime.utcnow() - timedelta(days=6)),
            "pro_old": Session(project_id=projects["pro"]["id"], user_id=user_ids["HistoryPro"], started_at=datetime.utcnow() - timedelta(days=61)),
            "pro_recent": Session(project_id=projects["pro"]["id"], user_id=user_ids["HistoryPro"], started_at=datetime.utcnow() - timedelta(days=59)),
            "studio_old": Session(project_id=projects["studio"]["id"], user_id=user_ids["HistoryStudio"], started_at=datetime.utcnow() - timedelta(days=365)),
        }
        db.session.add_all(sessions.values())
        db.session.commit()
        ids = {name: session.id for name, session in sessions.items()}
        purge_old_data()
        remaining = {session.id for session in Session.query.all()}

    assert ids["free_old"] not in remaining
    assert ids["pro_old"] not in remaining
    assert ids["free_recent"] in remaining
    assert ids["pro_recent"] in remaining
    assert ids["studio_old"] in remaining
