def test_health_and_frontend_assets(client):
    health = client.get("/health")
    assert health.status_code == 200
    assert health.get_json()["ok"] is True
    assert client.get("/").status_code == 200
    assert client.get("/app.js").status_code == 200
    assert client.get("/app.css").status_code == 200
    icon_library = client.get("/vendor/lucide.min.js")
    assert icon_library.status_code == 200
    assert b"createIcons" in icon_library.data


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


def test_registration_discloses_and_requires_tracking_consent(client):
    html = client.get("/").data
    javascript = client.get("/app.js").data
    assert b'id="regTrackingConsent"' in html
    assert b'type="checkbox" required' in html
    assert b"I consent to RoWatch session tracking" in html
    assert b'href="/terms"' in html
    assert b'href="/privacy"' in html
    assert b"What does RoWatch track?" in html
    assert b"tracking_consent: el('regTrackingConsent').checked" in javascript
    assert b'id="legalConsentDialog"' in html
    assert b'id="legalConsentCheckbox"' in html
    assert b"Updated terms require your approval" in html
    assert b"/auth/consent" in javascript

    privacy = client.get("/privacy")
    terms = client.get("/terms")
    assert privacy.status_code == 200
    assert terms.status_code == 200
    html = privacy.get_data(as_text=True)
    assert "Privacy Policy" in html and "Terms of Service" in html
    assert "does not upload script source code, record keystrokes" in html
    assert "not affiliated with, endorsed by, or sponsored by Roblox Corporation" in html
