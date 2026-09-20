from pathlib import Path
import os
import threading
import time

from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS

from config import Config
from models import db
from realtime import socketio


BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)

    CORS(app, supports_credentials=True)
    db.init_app(app)
    socketio.init_app(app)

    with app.app_context():
        from blueprints.auth import auth_bp
        from blueprints.projects import projects_bp
        from blueprints.events import events_bp
        from blueprints.dashboard import dashboard_bp
        from blueprints.payments import payments_bp
        from blueprints.workspace import workspace_bp, plugin_tasks_bp

        app.register_blueprint(auth_bp)
        app.register_blueprint(projects_bp)
        app.register_blueprint(events_bp)
        app.register_blueprint(dashboard_bp)
        app.register_blueprint(payments_bp)
        app.register_blueprint(workspace_bp)
        app.register_blueprint(plugin_tasks_bp)
        db.create_all()

    @app.get("/health")
    def health():
        return jsonify({"ok": True, "service": "rowatch"})

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def frontend(path):
        # API routes are handled by blueprints above. Everything else is the SPA.
        candidate = FRONTEND_DIR / path
        if path and candidate.is_file():
            return send_from_directory(FRONTEND_DIR, path)
        return send_from_directory(FRONTEND_DIR, "index.html")

    return app


def start_purge_thread(app):
    def purge_loop():
        while True:
            time.sleep(86400)
            with app.app_context():
                from utils import purge_old_data
                purge_old_data()
                print("[RoWatch] old tracking data purged")

    threading.Thread(target=purge_loop, daemon=True).start()


if __name__ == "__main__":
    app = create_app()
    if os.environ.get("ROWATCH_DISABLE_PURGE") != "1":
        start_purge_thread(app)
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=os.environ.get("FLASK_DEBUG", "1") == "1")
