import hashlib
import re
from datetime import datetime, timedelta

from app import create_app
from conftest import register
from models import UpgradeCode, User, db


def test_admin_bootstraps_from_environment_and_can_login(tmp_path, monkeypatch):
    monkeypatch.setenv("ROWATCH_ADMIN_USERNAME", "EnvAdmin")
    monkeypatch.setenv("ROWATCH_ADMIN_EMAIL", "env-admin@example.test")
    monkeypatch.setenv("ROWATCH_ADMIN_PASSWORD", "strong-admin-password")
    application = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'admin.db'}",
        "SECRET_KEY": "test-secret",
        "JWT_SECRET": "test-jwt",
    })
    client = application.test_client()
    login = client.post("/auth/login", json={"username": "EnvAdmin", "password": "strong-admin-password"})
    assert login.status_code == 200
    assert client.get("/auth/me").get_json()["is_admin"] is True
    with application.app_context():
        assert User.query.filter_by(username="EnvAdmin").count() == 1
        db.session.remove()
        db.drop_all()


def test_admin_code_generation_is_secure_and_list_is_masked(app, code_admin):
    response = code_admin.post("/payments/codes", json={
        "plan": "pro", "duration_days": 45, "quantity": 2, "note": "launch",
    })
    assert response.status_code == 201
    codes = response.get_json()["codes"]
    assert len(codes) == 2
    assert all(re.fullmatch(r"[0-9a-f]{64}", item["code"]) for item in codes)
    raw = codes[0]["code"]
    with app.app_context():
        stored = UpgradeCode.query.filter_by(code_prefix=raw[:8]).first()
        assert stored.code_hash == hashlib.sha256(raw.encode()).hexdigest()
        assert stored.code_hash != raw
    listed = code_admin.get("/payments/codes").get_json()
    listed_record = next(item for item in listed if item["masked_code"].startswith(raw[:8]))
    assert "code" not in listed_record and "code_hash" not in listed_record


def test_non_admin_cannot_manage_codes(registered_client):
    assert registered_client.post("/payments/codes", json={"plan": "pro", "duration_days": 30}).status_code == 403
    assert registered_client.get("/payments/codes").status_code == 403


def test_admin_code_validation_returns_client_errors(code_admin):
    invalid_number = code_admin.post("/payments/codes", json={"plan": "pro", "duration_days": "forever"})
    assert invalid_number.status_code == 400
    too_many = code_admin.post("/payments/codes", json={"plan": "studio", "duration_days": 30, "quantity": 101})
    assert too_many.status_code == 400


def test_code_is_single_use_and_paid_checkout_is_blocked(app, registered_client, issue_code):
    raw = issue_code("pro", 30)
    first = registered_client.post("/payments/codes/redeem", json={"code": raw})
    assert first.status_code == 200
    assert first.get_json()["plan"] == "pro"
    other = app.test_client()
    assert register(other, "OtherRedeemer").status_code == 201
    assert other.post("/payments/codes/redeem", json={"code": raw}).status_code == 409
    assert other.post("/payments/checkout", json={"plan": "pro", "duration_months": 1}).status_code == 400


def test_paid_accounts_cannot_downgrade_to_free(registered_client, issue_code):
    pro = registered_client.post("/payments/codes/redeem", json={"code": issue_code("pro", 30)})
    assert pro.status_code == 200
    pro_expiry = pro.get_json()["expires_at"]

    downgrade = registered_client.post("/payments/checkout", json={"plan": "free", "duration_months": 1})
    assert downgrade.status_code == 409
    account = registered_client.get("/payments/account").get_json()
    assert account["plan"] == "pro"
    assert account["expires_at"] == pro_expiry

    studio = registered_client.post("/payments/codes/redeem", json={"code": issue_code("studio", 30)})
    assert studio.status_code == 200
    studio_expiry = studio.get_json()["expires_at"]
    downgrade = registered_client.post("/payments/checkout", json={"plan": "free", "duration_months": 1})
    assert downgrade.status_code == 409
    account = registered_client.get("/payments/account").get_json()
    assert account["plan"] == "studio"
    assert account["expires_at"] == studio_expiry


def test_pro_can_upgrade_to_studio_and_remaining_time_is_preserved(app, registered_client, issue_code):
    assert registered_client.post("/payments/codes/redeem", json={"code": issue_code("pro", 20)}).status_code == 200
    with app.app_context():
        owner = User.query.filter_by(username="Owner").first()
        before = owner.subscription.expires_at
    upgraded = registered_client.post("/payments/codes/redeem", json={"code": issue_code("studio", 10)})
    assert upgraded.status_code == 200
    assert upgraded.get_json()["plan"] == "studio"
    with app.app_context():
        owner = User.query.filter_by(username="Owner").first()
        assert owner.subscription.expires_at - before == timedelta(days=10)


def test_studio_cannot_redeem_pro_and_code_remains_available(app, registered_client, issue_code):
    assert registered_client.post("/payments/codes/redeem", json={"code": issue_code("studio", 30)}).status_code == 200
    pro_code = issue_code("pro", 30)
    denied = registered_client.post("/payments/codes/redeem", json={"code": pro_code})
    assert denied.status_code == 409
    with app.app_context():
        record = UpgradeCode.query.filter_by(code_hash=hashlib.sha256(pro_code.encode()).hexdigest()).first()
        assert record.redeemed_at is None


def test_revoked_expired_and_malformed_codes_are_rejected(app, registered_client, code_admin, issue_code):
    revoked = issue_code("pro")
    records = code_admin.get("/payments/codes").get_json()
    record_id = next(item["id"] for item in records if item["masked_code"].startswith(revoked[:8]))
    assert code_admin.post(f"/payments/codes/{record_id}/revoke").status_code == 200
    assert registered_client.post("/payments/codes/redeem", json={"code": revoked}).status_code == 409
    assert registered_client.post("/payments/codes/redeem", json={"code": "not-a-code"}).status_code == 400

    expired = issue_code("studio")
    with app.app_context():
        record = UpgradeCode.query.filter_by(code_hash=hashlib.sha256(expired.encode()).hexdigest()).first()
        record.expires_at = datetime.utcnow() - timedelta(seconds=1)
        db.session.commit()
    assert registered_client.post("/payments/codes/redeem", json={"code": expired}).status_code == 410
