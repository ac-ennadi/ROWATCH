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
