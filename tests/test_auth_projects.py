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


def test_free_account_project_limit_and_account_upgrade(registered_client):
    first = registered_client.post("/projects/", json={"name": "One"})
    assert first.status_code == 201
    assert registered_client.post("/projects/", json={"name": "Blocked"}).status_code == 403

    upgraded = registered_client.post("/payments/checkout", json={
        "plan": "pro", "duration_months": 1, "method": "dummy",
    })
    assert upgraded.status_code == 200
    assert registered_client.post("/projects/", json={"name": "Two"}).status_code == 201
    assert registered_client.post("/projects/", json={"name": "Three"}).status_code == 201
    assert registered_client.post("/projects/", json={"name": "Four"}).status_code == 403
    assert all(item["plan"] == "pro" for item in registered_client.get("/projects/").get_json())


def test_member_inherits_project_owner_plan(app):
    owner = app.test_client()
    member = app.test_client()
    assert register(owner, "PlanOwner").status_code == 201
    assert register(member, "PlanMember").status_code == 201
    assert owner.post("/payments/checkout", json={"plan": "pro", "duration_months": 1}).status_code == 200
    project = owner.post("/projects/", json={"name": "Shared"}).get_json()
    assert owner.post(f"/projects/{project['id']}/members/invite", json={"username": "PlanMember"}).status_code == 201

    inherited = member.get(f"/projects/{project['id']}").get_json()
    assert inherited["plan"] == "pro"
    assert inherited["plan_owner"] == "PlanOwner"


def test_account_plan_lists_all_three_options(registered_client):
    data = registered_client.get("/payments/account").get_json()
    assert data["plan"] == "free"
    assert set(data["plans"]) == {"free", "pro", "studio"}
