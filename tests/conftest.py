import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app import create_app
from models import User, db


@pytest.fixture
def app(tmp_path):
    database = tmp_path / "test.db"
    application = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database}",
        "SECRET_KEY": "test-secret-key-at-least-32-bytes-long",
        "JWT_SECRET": "test-jwt-secret-at-least-32-bytes-long",
        "SESSION_COOKIE_SECURE": False,
    })
    yield application
    with application.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def register(client, username, email=None):
    return client.post("/auth/register", json={
        "username": username,
        "email": email or f"{username.lower()}@example.test",
        "password": "secret123",
        "tracking_consent": True,
    })


@pytest.fixture
def registered_client(client):
    response = register(client, "Owner")
    assert response.status_code == 201
    return client


@pytest.fixture
def project(registered_client):
    response = registered_client.post("/projects/", json={"name": "Test Project"})
    assert response.status_code == 201
    return response.get_json()


@pytest.fixture
def code_admin(app):
    admin = app.test_client()
    assert register(admin, "CodeAdmin").status_code == 201
    with app.app_context():
        user = User.query.filter_by(username="CodeAdmin").first()
        user.is_admin = True
        db.session.commit()
    return admin


@pytest.fixture
def issue_code(code_admin):
    def issue(plan="pro", duration_days=30, **extra):
        payload = {"plan": plan, "duration_days": duration_days, **extra}
        response = code_admin.post("/payments/codes", json=payload)
        assert response.status_code == 201, response.get_json()
        return response.get_json()["codes"][0]["code"]
    return issue



def issue_api_key(client):
    response = client.post("/auth/api-key", json={})
    assert response.status_code in (200, 201), response.get_json()
    raw = response.get_json().get("api_key")
    if not raw:
        regenerated = client.post("/auth/api-key/regenerate", json={})
        assert regenerated.status_code == 200
        raw = regenerated.get_json()["api_key"]
    return raw
