from conftest import issue_api_key, register
from config import PLAN_LIMITS
from models import db, ProjectMember, User


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
    token = issue_api_key(member)
    headers = {"X-Project-ID": project["id"], "X-API-Key": token}
    tasks = member.get("/api/tasks", headers=headers).get_json()
    assert [task["title"] for task in tasks] == ["Member only"]
    task_id = tasks[0]["id"]
    assert member.post(f"/api/tasks/{task_id}/complete", headers=headers, json={"completed": True}).status_code == 200



def test_custom_task_board_is_shared_and_studio_stays_flat(app):
    owner, member, _, project, members = setup_team(app)
    base = f"/workspace/{project['id']}"
    board = owner.get(f"{base}/tasks").get_json()
    assert [column["name"] for column in board["columns"]] == ["Backlog", "To do", "In progress", "Done"]
    backlog, _, _, done = board["columns"]

    review_response = owner.post(f"{base}/task-columns", json={"name": "Review"})
    assert review_response.status_code == 201
    review = review_response.get_json()
    renamed = owner.patch(f"{base}/task-columns/{review['id']}", json={"name": "Ready for review"})
    assert renamed.status_code == 200
    assert renamed.get_json()["name"] == "Ready for review"

    column_ids = [review["id"], backlog["id"]] + [
        column["id"] for column in board["columns"] if column["id"] not in (backlog["id"], done["id"])
    ] + [done["id"]]
    reordered = owner.put(f"{base}/task-columns/reorder", json={"column_ids": column_ids})
    assert reordered.status_code == 200
    assert [column["id"] for column in reordered.get_json()] == column_ids

    member_id = next(item["user_id"] for item in members if item["username"] == "TeamMember")
    first = owner.post(f"{base}/tasks", json={
        "title": "Task A", "column_id": backlog["id"], "assignee_ids": [member_id],
    }).get_json()
    second = owner.post(f"{base}/tasks", json={
        "title": "Task C", "column_id": review["id"], "assignee_ids": [member_id],
    }).get_json()
    moved = owner.post(f"{base}/tasks/{first['id']}/move", json={"column_id": review["id"], "position": 0})
    assert moved.status_code == 200
    assert moved.get_json()["column_id"] == review["id"]

    refused = owner.delete(f"{base}/task-columns/{review['id']}", json={})
    assert refused.status_code == 409
    assert refused.get_json()["destination_required"] is True
    deleted = owner.delete(
        f"{base}/task-columns/{review['id']}", json={"destination_column_id": done["id"]},
    )
    assert deleted.status_code == 200
    assert deleted.get_json()["moved_tasks"] == 2
    tasks = owner.get(f"{base}/tasks").get_json()["items"]
    assert {item["id"]: item["column_id"] for item in tasks} == {first["id"]: done["id"], second["id"]: done["id"]}

    token = issue_api_key(member)
    studio_tasks = member.get(
        "/api/v1/tasks", headers={"X-Project-ID": project["id"], "X-API-Key": token},
    ).get_json()
    assert {task["title"] for task in studio_tasks} == {"Task A", "Task C"}
    assert member.post(f"{base}/task-columns", json={"name": "Forbidden"}).status_code == 403
    assert member.post(f"{base}/tasks/{first['id']}/move", json={"column_id": backlog["id"], "position": 0}).status_code == 403

def test_members_read_docs_but_only_admins_write(app):
    owner, member, outsider, project, _ = setup_team(app)
    created = owner.post(f"/workspace/{project['id']}/documents", json={"title": "Guide", "content_md": "# Guide"})
    assert created.status_code == 201
    documents = member.get(f"/workspace/{project['id']}/documents")
    assert documents.status_code == 200
    document = documents.get_json()["items"][0]
    assert document["title"] == "Guide"
    assert document["created_by"] == "TeamOwner"
    assert document["updated_by"] == "TeamOwner"
    assert member.post(f"/workspace/{project['id']}/documents", json={"title": "Forbidden"}).status_code == 403
    assert outsider.get(f"/workspace/{project['id']}/documents").status_code == 403

    with app.app_context():
        team_member = User.query.filter_by(username="TeamMember").one()
        membership = ProjectMember.query.filter_by(project_id=project["id"], user_id=team_member.id).one()
        membership.role = "co_admin"
        db.session.commit()
    modified = member.patch(
        f"/workspace/{project['id']}/documents/{document['id']}",
        json={"content_md": "# Updated guide"},
    )
    assert modified.status_code == 200
    assert modified.get_json()["created_by"] == "TeamOwner"
    assert modified.get_json()["updated_by"] == "TeamMember"


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


def test_workspace_names_and_free_document_words_are_limited(registered_client, project, issue_code):
    base = f"/workspace/{project['id']}"
    too_long = "x" * 33
    assert registered_client.post(f"{base}/tasks", json={"title": too_long}).status_code == 400
    task = registered_client.post(f"{base}/tasks", json={"title": "Valid task"}).get_json()
    assert registered_client.patch(f"{base}/tasks/{task['id']}", json={"title": too_long}).status_code == 400
    assert registered_client.post(f"{base}/documents", json={"title": too_long}).status_code == 400
    document = registered_client.post(f"{base}/documents", json={"title": "Valid guide", "content_md": "short"}).get_json()
    assert registered_client.patch(f"{base}/documents/{document['id']}", json={"title": too_long}).status_code == 400

    oversized_content = "word " * 1029
    assert registered_client.patch(
        f"{base}/documents/{document['id']}", json={"content_md": oversized_content}
    ).status_code == 400
    rejected = registered_client.post(f"{base}/documents", json={
        "title": "Free guide",
        "content_md": oversized_content,
    })
    assert rejected.status_code == 400
    assert rejected.get_json()["word_limit"] == 1028
    assert rejected.get_json()["word_count"] == 1029

    assert registered_client.post("/payments/codes/redeem", json={"code": issue_code("pro")}).status_code == 200
    accepted = registered_client.post(f"{base}/documents", json={
        "title": "Pro guide",
        "content_md": oversized_content,
    })
    assert accepted.status_code == 201
