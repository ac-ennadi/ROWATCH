from realtime import socketio
from conftest import issue_api_key
from models import db, Project, ProjectMember, ScriptEvent, Session, User


def test_plugin_auth_rejects_bad_key(registered_client):
    token = issue_api_key(registered_client)
    response = registered_client.get("/api/events/ping", headers={
        "X-Project-ID": "bad", "X-API-Key": token,
    })
    assert response.status_code == 404
    assert response.get_json()["error"] == "Project not found"


def test_studio_session_script_and_instance_stats(registered_client, project):
    token = issue_api_key(registered_client)
    headers = {"X-Project-ID": project["id"], "X-API-Key": token}
    session_id = registered_client.post("/api/events/session/start", headers=headers).get_json()["session_id"]
    assert registered_client.post("/api/events/script/open", headers=headers, json={"session_id": session_id, "script": "Workspace.Main"}).status_code == 200
    closed = registered_client.post("/api/events/script/close", headers=headers, json={
        "session_id": session_id, "script": "Workspace.Main", "chars_added": 12, "chars_removed": 3,
    })
    assert closed.status_code == 200
    instances = registered_client.post("/api/events/instance/change", headers=headers, json={
        "session_id": session_id,
        "events": [
            {"category": "part", "action": "added", "class_name": "Part", "instance_name": "Workspace.Part", "count": 2},
            {"category": "ui", "action": "removed", "class_name": "Frame", "instance_name": "StarterGui.Menu", "count": 1},
        ],
    })
    assert instances.status_code == 200
    assert registered_client.post("/api/events/session/heartbeat", headers=headers, json={"session_id": session_id}).status_code == 200
    assert registered_client.post("/api/events/session/end", headers=headers, json={"session_id": session_id}).status_code == 200

    stats = registered_client.get(f"/dashboard/{project['id']}/overview").get_json()["members"][0]["stats"]
    assert stats["chars_added"] == 12
    assert stats["chars_removed"] == 3
    assert stats["parts_added"] == 2
    assert stats["ui_removed"] == 1


def test_authenticated_socket_room_receives_project_updates(app, registered_client, project):
    token = issue_api_key(registered_client)
    socket_client = socketio.test_client(app, flask_test_client=registered_client)
    assert socket_client.is_connected()
    socket_client.emit("join_project", {"project_id": project["id"]})
    joined = socket_client.get_received()
    assert any(item["name"] == "project_joined" and item["args"][0]["ok"] for item in joined)

    response = registered_client.post("/api/events/session/start", headers={"X-Project-ID": project["id"], "X-API-Key": token})
    assert response.status_code == 200
    updates = socket_client.get_received()
    assert any(item["name"] == "project_update" and item["args"][0]["type"] == "session_started" for item in updates)
    socket_client.disconnect()


def test_session_end_and_script_events_are_scoped_to_selected_project(app, registered_client, project):
    api_key = issue_api_key(registered_client)
    project_a_headers = {"X-Project-ID": project["id"], "X-API-Key": api_key}
    session_id = registered_client.post("/api/events/session/start", headers=project_a_headers).get_json()["session_id"]

    with app.app_context():
        owner = User.query.filter_by(username="Owner").one()
        project_b = Project(name="Second Project", owner_id=owner.id)
        db.session.add(project_b)
        db.session.flush()
        db.session.add(ProjectMember(project_id=project_b.id, user_id=owner.id, role="owner"))
        db.session.commit()
        project_b_id = project_b.id

    project_b_headers = {"X-Project-ID": project_b_id, "X-API-Key": api_key}
    body = {"session_id": session_id, "script": "Workspace.Main"}
    assert registered_client.post("/api/events/script/open", headers=project_b_headers, json=body).status_code == 404
    assert registered_client.post("/api/events/script/close", headers=project_b_headers, json=body).status_code == 404
    assert registered_client.post("/api/events/session/end", headers=project_b_headers, json={"session_id": session_id}).status_code == 404

    with app.app_context():
        assert db.session.get(Session, session_id).ended_at is None
        assert ScriptEvent.query.filter_by(session_id=session_id).count() == 0

    assert registered_client.post("/api/events/session/end", headers=project_a_headers, json={"session_id": session_id}).status_code == 200


def test_script_close_rejects_an_ended_session(app, registered_client, project):
    api_key = issue_api_key(registered_client)
    headers = {"X-Project-ID": project["id"], "X-API-Key": api_key}
    session_id = registered_client.post("/api/events/session/start", headers=headers).get_json()["session_id"]
    assert registered_client.post("/api/events/session/end", headers=headers, json={"session_id": session_id}).status_code == 200

    response = registered_client.post("/api/events/script/close", headers=headers, json={
        "session_id": session_id,
        "script": "Workspace.AfterEnd",
        "chars_added": 500,
    })
    assert response.status_code == 404
    assert response.get_json()["error"] == "Active session not found"
    with app.app_context():
        assert ScriptEvent.query.filter_by(session_id=session_id).count() == 0
