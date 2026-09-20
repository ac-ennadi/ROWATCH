from conftest import register


def test_auth_cookie_survives_followup_requests(client):
    assert register(client, "Persistent").status_code == 201
    me = client.get("/auth/me")
    assert me.status_code == 200
    assert me.get_json()["username"] == "Persistent"
    assert me.get_json()["plan"] == "free"


def test_logout_invalidates_cookie(registered_client):
    assert registered_client.post("/auth/logout").status_code == 200
    assert registered_client.get("/auth/me").status_code == 401


def test_free_account_project_limit_and_account_upgrade(registered_client, issue_code):
    first = registered_client.post("/projects/", json={"name": "One"})
    assert first.status_code == 201
    assert registered_client.post("/projects/", json={"name": "Blocked"}).status_code == 403

    upgraded = registered_client.post("/payments/codes/redeem", json={"code": issue_code("pro")})
    assert upgraded.status_code == 200
    assert registered_client.post("/projects/", json={"name": "Two"}).status_code == 201
    assert registered_client.post("/projects/", json={"name": "Three"}).status_code == 201
    assert registered_client.post("/projects/", json={"name": "Four"}).status_code == 403
    assert all(item["plan"] == "pro" for item in registered_client.get("/projects/").get_json())


def test_member_inherits_project_owner_plan(app, issue_code):
    owner = app.test_client()
    member = app.test_client()
    assert register(owner, "PlanOwner").status_code == 201
    assert register(member, "PlanMember").status_code == 201
    assert owner.post("/payments/codes/redeem", json={"code": issue_code("pro")}).status_code == 200
    project = owner.post("/projects/", json={"name": "Shared"}).get_json()
    assert owner.post(f"/projects/{project['id']}/members/invite", json={"username": "PlanMember"}).status_code == 201

    inherited = member.get(f"/projects/{project['id']}").get_json()
    assert inherited["plan"] == "pro"
    assert inherited["plan_owner"] == "PlanOwner"


def test_account_plan_lists_all_three_options(registered_client):
    data = registered_client.get("/payments/account").get_json()
    assert data["plan"] == "free"
    assert set(data["plans"]) == {"free", "pro", "studio"}


def test_registration_requires_explicit_tracking_consent(client):
    payload = {
        "username": "NoConsent",
        "email": "no-consent@example.test",
        "password": "secret123",
    }
    missing = client.post("/auth/register", json=payload)
    assert missing.status_code == 400
    assert missing.get_json()["consent_required"] is True

    declined = client.post("/auth/register", json={**payload, "tracking_consent": False})
    assert declined.status_code == 400
    assert declined.get_json()["consent_required"] is True


def test_registration_records_versioned_tracking_consent(app, client):
    response = register(client, "Consented")
    assert response.status_code == 201
    me = client.get("/auth/me").get_json()
    assert me["tracking_consent_at"] is not None
    assert me["tracking_consent_version"] == "2026-08-25"

    with app.app_context():
        from models import User
        user = User.query.filter_by(username="Consented").one()
        assert user.tracking_consent_at is not None
        assert user.tracking_consent_version == "2026-08-25"
