def test_health_and_frontend_assets(client):
    health = client.get("/health")
    assert health.status_code == 200
    assert health.get_json()["ok"] is True
    assert client.get("/").status_code == 200
    assert client.get("/app.js").status_code == 200
    assert client.get("/app.css").status_code == 200


def test_spa_fallback(client):
    response = client.get("/some/client/route")
    assert response.status_code == 200
    assert b"RoWatch" in response.data


def test_official_plugin_download_is_available_in_public_and_dashboard_ui(client):
    url = b"https://create.roblox.com/store/asset/92589984687196/RoWatch-Beta"
    landing = client.get("/").data
    app_js = client.get("/app.js").data
    assert url in landing
    assert url in app_js
    assert b'target="_blank"' in landing
    assert b'rel="noopener noreferrer"' in landing
