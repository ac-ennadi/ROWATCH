import hashlib
import re

from conftest import issue_api_key, register
from models import AccountApiKey, Project, ProjectMember, User, db


def test_email_password_registration_and_login(client):
    response = register(client, username="account_user", email="account@example.com")
    assert response.status_code == 201
    client.post("/auth/logout")

    by_email = client.post("/auth/login", json={
        "email": "account@example.com", "password": "secret123",
    })
    assert by_email.status_code == 200
    client.post("/auth/logout")
    by_username = client.post("/auth/login", json={
        "username": "account_user", "password": "secret123",
    })
    assert by_username.status_code == 200


def test_api_key_is_one_time_and_only_hash_is_stored(app, registered_client):
    response = registered_client.post("/auth/api-key")
    assert response.status_code == 201
    raw = response.get_json()["api_key"]
    assert re.fullmatch(r"[0-9a-f]{64}", raw)

    with app.app_context():
        record = AccountApiKey.query.one()
        assert record.key_hash == hashlib.sha256(raw.encode()).hexdigest()
        assert raw != record.key_hash

    assert "api_key" not in registered_client.post("/auth/api-key").get_json()
    status = registered_client.get("/auth/api-key").get_json()
    assert status["configured"] is True
    assert status["masked_key"] == f"{raw[:12]}..."
    assert "api_key" not in status


def test_regeneration_invalidates_previous_key(registered_client, project):
    old_key = issue_api_key(registered_client)
    headers = {"X-API-Key": old_key, "X-Project-ID": project["id"]}
    assert registered_client.get("/api/events/ping", headers=headers).status_code == 200

    new_key = registered_client.post("/auth/api-key/regenerate").get_json()["api_key"]
    assert new_key != old_key
    assert registered_client.get("/api/events/ping", headers=headers).status_code == 401
    headers["X-API-Key"] = new_key
    assert registered_client.get("/api/events/ping", headers=headers).status_code == 200


def test_plugin_lists_only_projects_for_api_key_owner(app, registered_client, project):
    key = issue_api_key(registered_client)
    with app.app_context():
        outsider = User(username="outsider", email="out@example.com", password_hash="unused")
        hidden = Project(name="Hidden", owner=outsider)
        db.session.add_all([outsider, hidden])
        db.session.flush()
        db.session.add(ProjectMember(project_id=hidden.id, user_id=outsider.id, role="owner"))
        db.session.commit()

    response = registered_client.get("/api/plugin/projects", headers={"X-API-Key": key})
    assert response.status_code == 200
    assert response.get_json()["projects"] == [{
        "id": project["id"], "name": project["name"], "role": "owner", "plan": "free",
    }]


def test_studio_rejects_old_shared_key_and_username_headers(registered_client, project):
    response = registered_client.get("/api/events/ping", headers={
        "X-Project-Key": "legacy-shared-key", "X-Username": "alice",
    })
    assert response.status_code == 401
    assert response.get_json()["api_key_required"] is True
