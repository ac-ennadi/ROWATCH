# RoWatch Full-Stack Starter

A clean RoWatch landing page + authenticated project dashboard for Roblox Studio development tracking.

## Included

- `frontend/` — vanilla HTML/CSS/JS SPA
  - public landing page
  - login / registration
  - **Login → My Projects → Project Dashboard** flow
  - persistent project sidebar
  - Overview, Activity, Tasks, Documentation, Analytics, Members, Studio Integration, Project Settings
  - **← My Projects** sidebar action
  - account controls
  - light + dark themes
  - restrained Roblox-Studio-blue accent (`#0B6FEA`)
- `backend/` — Flask + SQLAlchemy API
  - JWT cookie auth
  - project CRUD and roles
  - multi-assignee tasks with per-member completion
  - Markdown project documentation
  - dashboard analytics with authenticated Socket.IO live updates
  - Studio plugin event API for scripts, parts, and UI components
  - demo plan checkout
- `plugin/RoWatch.lua` — multi-project Roblox Studio plugin with saved project buttons

## Run locally

```bash
cd backend
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open: `http://localhost:5000`

The Flask app serves the files from `../frontend`, so you only need one process for local development. Logged-in users return to My Projects after a browser refresh.

## Run with Docker on Linux

Requirements: Docker Engine with the Compose plugin.

```bash
# Edit the root .env and set strong SECRET_KEY and JWT_SECRET values, then run:
docker compose up --build -d
```

Open `http://localhost:5000`. View status and logs with:

```bash
docker compose ps
docker compose logs -f rowatch
```

Stop the application with `docker compose down`. User and project data is stored in
the `rowatch_data` Docker volume and survives container replacement. To use a
different host port, set `ROWATCH_PORT` in `.env`.

For a direct image build without Compose:

```bash
docker build -t rowatch .
docker run --name rowatch -p 5000:5000 \
  -e SECRET_KEY='replace-me' \
  -e JWT_SECRET='replace-me-too' \
  -e DATABASE_URL='sqlite:////app/instance/rowatch.db' \
  -v rowatch_data:/app/instance \
  rowatch
```

## User pipeline

```text
Landing
  → Login
  → My Projects
  → Select Project
  → Dashboard + Sidebar
       ├─ Overview
       ├─ Activity
       ├─ Analytics (admin)
       ├─ Members (admin)
       ├─ Studio Integration
       ├─ Project Settings (admin)
       ├─ ← My Projects
       ├─ Theme
       ├─ Account
       └─ Log out
```

## Backend routes

### Web auth
- `POST /auth/register`
- `POST /auth/login`
- `POST /auth/logout`
- `GET /auth/me`
- `PATCH /auth/me`

### Projects
- `GET /projects/`
- `POST /projects/`
- `GET /projects/<id>`
- `PATCH /projects/<id>` owner only
- `DELETE /projects/<id>` owner only
- member/invite/role/key routes retained

### Team workspace
- `GET/POST /workspace/<id>/tasks`
- `PATCH/DELETE /workspace/<id>/tasks/<task_id>`
- `POST /workspace/<id>/tasks/<task_id>/complete`
- `GET/POST /workspace/<id>/documents`
- `PATCH/DELETE /workspace/<id>/documents/<document_id>`
- `GET /api/tasks` Studio member task list
- `POST /api/tasks/<task_id>/complete` Studio completion toggle

### Dashboard
- `GET /dashboard/<id>/me`
- `GET /dashboard/<id>/overview`
- `GET /dashboard/<id>/activity`
- `GET /dashboard/<id>/charts/daily`

### Roblox Studio plugin
All plugin endpoints require:

```http
X-Project-Key: <project key>
X-Username: <rowatch username>
```

Routes:
- `GET /api/events/ping`
- `POST /api/events/session/start`
- `POST /api/events/session/end`
- `POST /api/events/session/heartbeat`
- `POST /api/events/script/open`
- `POST /api/events/script/close`
- `POST /api/events/instance/change`

## Live dashboard and Studio tracking

The web dashboard joins an authenticated Socket.IO room for the selected project.
Session starts, heartbeats, script changes, and part/UI changes refresh the active
Overview, Activity, or Analytics panel automatically. The default Docker setup uses
one Gunicorn worker so the in-process live event channel works without Redis.

The Studio plugin stores multiple validated project profiles in plugin settings.
Use **Add Project** once per project, then start future sessions from its project
button. Tracking runs only during an active session and records `BasePart` plus
`GuiObject`/`LayerCollector` additions and removals.


Tasks can be assigned to multiple members. Each assignment has its own completion
state, so shared work remains open for every member who has not checked it off. The
Studio plugin shows only tasks assigned to the saved profile username and allows
that member to complete or reopen them.

Documentation supports multiple Markdown pages with a live rendered preview. All
project members can read tasks and documents; owners and co-admins manage them.

## Production notes

Before production:
- set strong `SECRET_KEY` and `JWT_SECRET`
- use Postgres through `DATABASE_URL`
- replace the dummy payment endpoint with your payment provider
- serve Flask with gunicorn/uwsgi behind a reverse proxy
- configure the Studio plugin `ROWATCH_URL` to the production server
