import os
from datetime import timedelta

class Config:
    SECRET_KEY          = os.environ.get("SECRET_KEY")
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///rowatch.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JWT_SECRET          = os.environ.get("JWT_SECRET")
    SESSION_DAYS        = int(os.environ.get("ROWATCH_SESSION_DAYS", "7"))
    JWT_EXPIRY          = timedelta(days=SESSION_DAYS)
    TRACKING_CONSENT_VERSION = os.environ.get("ROWATCH_TRACKING_CONSENT_VERSION", "2026-08-25")
    MAX_CONTENT_LENGTH = int(os.environ.get("ROWATCH_MAX_REQUEST_BYTES", str(1024 * 1024)))
    SESSION_COOKIE_SECURE = os.environ.get("ROWATCH_SECURE_COOKIES", "1") == "1"
    TRUSTED_ORIGINS = tuple(v.strip().rstrip("/") for v in os.environ.get("ROWATCH_TRUSTED_ORIGINS", "").split(",") if v.strip())

PLAN_PRICES = {
    "pro":    {"monthly": 5.99,  "yearly": 49.99},
    "studio": {"monthly": 14.99, "yearly": 119.99},
}

PLAN_LIMITS = {
    "free":   {"projects": 1,    "members": 5,  "history_days": 7,   "co_admins": 0,    "export": False, "tasks": 10,  "documents": 3},
    "pro":    {"projects": 3,    "members": 15, "history_days": 60,  "co_admins": 1,    "export": True,  "tasks": None,"documents": None},
    "studio": {"projects": None, "members": None,"history_days": None,"co_admins": None, "export": True,  "tasks": None,"documents": None},
}
