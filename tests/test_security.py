from conftest import issue_api_key


def test_security_headers_and_cross_origin_posts(client):
    response = client.get("/")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
    blocked = client.post("/auth/login", headers={"Origin": "https://evil.example"}, json={"username": "x", "password": "x"})
    assert blocked.status_code == 403


def test_login_is_rate_limited(client):
    for _ in range(10):
        assert client.post("/auth/login", json={"username": "brute", "password": "wrong"}).status_code == 401
    assert client.post("/auth/login", json={"username": "brute", "password": "wrong"}).status_code == 429


def test_malformed_plugin_numbers_are_rejected(registered_client, project):
    key = issue_api_key(registered_client)
    headers = {"X-API-Key": key, "X-Project-ID": project["id"]}
    session_id = registered_client.post("/api/events/session/start", headers=headers).get_json()["session_id"]
    close = registered_client.post("/api/events/script/close", headers=headers, json={
        "session_id": session_id, "script": "Workspace.Main", "chars_added": "invalid",
    })
    assert close.status_code == 400
    instances = registered_client.post("/api/events/instance/change", headers=headers, json={
        "session_id": session_id, "events": ["invalid", {"category": "part", "action": "added", "count": "invalid"}],
    })
    assert instances.status_code == 400


def test_request_body_limit(client):
    response = client.post("/auth/register", data=b"x" * (1024 * 1024 + 1), content_type="application/json")
    assert response.status_code == 413
