import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app import create_app
from models import db


@pytest.fixture
def app(tmp_path):
    database = tmp_path / "test.db"
    application = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database}",
        "SECRET_KEY": "test-secret",
        "JWT_SECRET": "test-jwt-secret",
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
        "password": "secret1",
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
