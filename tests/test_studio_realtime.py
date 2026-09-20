from realtime import socketio


def plugin_headers(project):
    return {"X-Project-Key": project["project_key"], "X-Username": "Owner"}


def test_plugin_auth_rejects_bad_key(registered_client):
    response = registered_client.get("/api/events/ping", headers={
        "X-Project-Key": "bad", "X-Username": "Owner",
    })
    assert response.status_code == 401
    assert response.get_json()["error"] == "Invalid project key"


def test_studio_session_script_and_instance_stats(registered_client, project):
    headers = plugin_headers(project)
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
    socket_client = socketio.test_client(app, flask_test_client=registered_client)
    assert socket_client.is_connected()
    socket_client.emit("join_project", {"project_id": project["id"]})
    joined = socket_client.get_received()
    assert any(item["name"] == "project_joined" and item["args"][0]["ok"] for item in joined)

    response = registered_client.post("/api/events/session/start", headers=plugin_headers(project))
    assert response.status_code == 200
    updates = socket_client.get_received()
    assert any(item["name"] == "project_update" and item["args"][0]["type"] == "session_started" for item in updates)
    socket_client.disconnect()
