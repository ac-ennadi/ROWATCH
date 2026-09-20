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


def test_studio_integration_is_part_of_project_settings_navigation(client):
    html = client.get("/").get_data(as_text=True)
    javascript = client.get("/app.js").get_data(as_text=True)
    assert 'data-panel="integration"' not in html
    assert 'data-panel="settings"' in html
    assert 'data-panel="settings" class="admin-only"' not in html
    assert "Roblox Studio connection" in javascript
    assert "Currently online" in javascript
    assert "Last seen" in javascript


def test_project_wiki_ui_exposes_list_graph_links_and_backlinks(client):
    javascript = client.get("/app.js").get_data(as_text=True)
    stylesheet = client.get("/app.css").get_data(as_text=True)
    assert "documents/graph" in javascript
    assert "wikiAutocomplete" in javascript
    assert "Backlinks" in javascript
    assert "unresolved_links" in javascript
    assert "data-graph-document" in javascript
    assert "wireDocumentGraph" in javascript
    assert "data-graph-zoom" in javascript
    assert "addEventListener('wheel'" in javascript
    assert "addEventListener('pointerdown'" in javascript
    assert ".document-graph" in stylesheet
    assert ".document-graph-world" in stylesheet
    assert "touch-action:none" in stylesheet


def test_task_toolbar_hides_shown_and_unlimited_indicators(client):
    javascript = client.get("/app.js").get_data(as_text=True)
    assert "shown ·" not in javascript
    assert "taskUsage.limit === null ? ''" in javascript
    usage = javascript.index("${taskUsageBadge}<label>Filter by assignee")
    add_column = javascript.index("addTaskColumnButton", usage)
    assert usage < add_column
