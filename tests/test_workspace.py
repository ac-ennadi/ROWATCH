from conftest import register
from config import PLAN_LIMITS


def setup_team(app):
    owner = app.test_client()
    member = app.test_client()
    outsider = app.test_client()
    assert register(owner, "TeamOwner").status_code == 201
    assert register(member, "TeamMember").status_code == 201
    assert register(outsider, "Outsider").status_code == 201
    project = owner.post("/projects/", json={"name": "Team"}).get_json()
    assert owner.post(f"/projects/{project['id']}/members/invite", json={"username": "TeamMember"}).status_code == 201
    members = owner.get(f"/projects/{project['id']}/members").get_json()
    return owner, member, outsider, project, members


def test_multi_assignee_completion_is_independent(app):
    owner, member, _, project, members = setup_team(app)
    task_response = owner.post(f"/workspace/{project['id']}/tasks", json={
        "title": "Shared task",
        "description_md": "## Acceptance criteria",
        "assignee_ids": [item["user_id"] for item in members],
    })
    assert task_response.status_code == 201
    task = task_response.get_json()
    assert len(task["assignments"]) == 2

    assert member.post(f"/workspace/{project['id']}/tasks/{task['id']}/complete", json={"completed": True}).status_code == 200
    refreshed = owner.get(f"/workspace/{project['id']}/tasks").get_json()["items"][0]
    states = {item["username"]: item["completed"] for item in refreshed["assignments"]}
    assert states == {"TeamOwner": False, "TeamMember": True}


def test_studio_tasks_are_filtered_to_authenticated_member(app):
    owner, member, _, project, members = setup_team(app)
    member_id = next(item["user_id"] for item in members if item["username"] == "TeamMember")
    owner_id = next(item["user_id"] for item in members if item["username"] == "TeamOwner")
    owner.post(f"/workspace/{project['id']}/tasks", json={"title": "Member only", "assignee_ids": [member_id]})
    owner.post(f"/workspace/{project['id']}/tasks", json={"title": "Owner only", "assignee_ids": [owner_id]})
    headers = {"X-Project-Key": project["project_key"], "X-Username": "TeamMember"}
    tasks = member.get("/api/tasks", headers=headers).get_json()
    assert [task["title"] for task in tasks] == ["Member only"]
    task_id = tasks[0]["id"]
    assert member.post(f"/api/tasks/{task_id}/complete", headers=headers, json={"completed": True}).status_code == 200


def test_members_read_docs_but_only_admins_write(app):
    owner, member, outsider, project, _ = setup_team(app)
    created = owner.post(f"/workspace/{project['id']}/documents", json={"title": "Guide", "content_md": "# Guide"})
    assert created.status_code == 201
    documents = member.get(f"/workspace/{project['id']}/documents")
    assert documents.status_code == 200
    assert documents.get_json()["items"][0]["title"] == "Guide"
    assert member.post(f"/workspace/{project['id']}/documents", json={"title": "Forbidden"}).status_code == 403
    assert outsider.get(f"/workspace/{project['id']}/documents").status_code == 403


def test_free_limits_and_pro_unlimited(app, monkeypatch, issue_code):
    monkeypatch.setitem(PLAN_LIMITS["free"], "tasks", 1)
    monkeypatch.setitem(PLAN_LIMITS["free"], "documents", 1)
    owner = app.test_client()
    assert register(owner, "LimitOwner").status_code == 201
    project = owner.post("/projects/", json={"name": "Limits"}).get_json()
    base = f"/workspace/{project['id']}"
    assert owner.post(f"{base}/tasks", json={"title": "One"}).status_code == 201
    assert owner.post(f"{base}/tasks", json={"title": "Two"}).status_code == 403
    assert owner.post(f"{base}/documents", json={"title": "One"}).status_code == 201
    assert owner.post(f"{base}/documents", json={"title": "Two"}).status_code == 403

    assert owner.post("/payments/codes/redeem", json={"code": issue_code("pro")}).status_code == 200
    assert owner.post(f"{base}/tasks", json={"title": "Two"}).status_code == 201
    assert owner.post(f"{base}/documents", json={"title": "Two"}).status_code == 201
