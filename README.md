# RoWatch Full-Stack Starter

A clean RoWatch landing page + authenticated project dashboard for Roblox Studio development tracking.

## Included

- `frontend/` - vanilla HTML/CSS/JS SPA
  - public landing page
  - login / registration
  - **Login → My Projects → Project Dashboard** flow
  - persistent project sidebar
  - Overview, Activity, Tasks, Documentation, Analytics, Members, Studio Integration, Project Settings
  - **← My Projects** sidebar action
  - account controls
  - light + dark themes
  - restrained Roblox-Studio-blue accent (`#0B6FEA`)
- `backend/` - Flask + SQLAlchemy API
  - JWT cookie auth
  - project CRUD and roles
  - multi-assignee tasks with per-member completion
  - Markdown project documentation
  - dashboard analytics with authenticated Socket.IO live updates
  - Studio plugin event API for scripts, parts, and UI components
  - account-level Free / Pro / Studio plan checkout
- `plugin/RoWatch.lua` - multi-project Roblox Studio plugin with saved project buttons

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
# Copy .env.orig to .env, then set strong secrets and admin credentials:
cp .env.orig .env
docker compose up --build -d
```

Open `http://localhost:5000`. View status and logs with:

```bash
docker compose ps
docker compose logs -f rowatch
```

Stop the application with `docker compose down`. User and project data is stored in
the `rowatch_data` Docker volume and survives container replacement. To use a
different host port, set `ROWATCH_PORT` in `.env`. The startup admin account is controlled by
`ROWATCH_ADMIN_USERNAME`, `ROWATCH_ADMIN_EMAIL`, and `ROWATCH_ADMIN_PASSWORD`
(the password must contain at least 12 characters).

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

## Account and Studio authentication

Users register and sign in with an email address and password. The Account screen
creates a 64-character API key that can be pasted into the Studio plugin. The plugin
then fetches every project that account belongs to and lets the user select one.

The raw API key is shown only when it is first created or regenerated; the server stores
only its SHA-256 hash. Regenerating it invalidates the previous key immediately. Studio
activity is attributed to the account that owns the key, so Roblox usernames and shared
project keys are not used for authentication.

The static administrator account is configured with `ROWATCH_ADMIN_USERNAME`,
`ROWATCH_ADMIN_EMAIL`, and `ROWATCH_ADMIN_PASSWORD`.

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
- `PUT /auth/password`
- `GET/POST /auth/api-key`
- `POST /auth/api-key/regenerate`

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
X-API-Key: <account API key>
X-Project-ID: <selected project ID>
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

The Studio plugin stores the account API key and its fetched project list in plugin
settings. Select a project button to start a session, or refresh memberships after an
invite or removal. Tracking runs only during an active session and records `BasePart` plus
`GuiObject`/`LayerCollector` additions and removals.


Free projects include up to **10 tasks** and **3 Markdown documents**. Pro and
Studio projects have unlimited tasks and documentation; limits are enforced by the
API and shown in the workspace UI.

Tasks can be assigned to multiple members. Each assignment has its own completion
state, so shared work remains open for every member who has not checked it off. The
Studio plugin shows only tasks assigned to the authenticated account and allows
that member to complete or reopen them.

Documentation supports multiple Markdown pages with a live rendered preview. All
project members can read tasks and documents; owners and co-admins manage them.

## Account-level plans

Plans belong to user accounts, not projects. Every project owned by an account uses
that owner's active plan for project count, members, history, co-admins, tasks,
documents, and exports. Invited members see the owner's effective capabilities but
manage their own subscription separately from Account.

Free, Pro, and Studio selection and expiry information are available only in the
Account screen. Existing paid project plans are migrated once at startup to the
owner's best active account plan.

## Automated tests

Install the test dependencies and run the same regression suite used by CI:

```bash
python -m pip install -r requirements-dev.txt
pytest -q
```

[`.github/workflows/tests.yml`](.github/workflows/tests.yml) runs automatically on
every push and pull request. The suite uses an isolated temporary SQLite database
and covers authentication cookies, logout, project/account plan limits, owner-plan
inheritance, project membership, task assignment and independent completion,
Markdown document permissions, Studio authentication/events, instance statistics,
Socket.IO project rooms, health checks, frontend assets, and SPA fallback routing.
A failing test makes the GitHub Actions check fail.

## Production notes

Before production:
- set strong `SECRET_KEY` and `JWT_SECRET`
- keep `ROWATCH_CORS_ENABLED=0` for same-origin-only browser access; to enable cross-origin access, set it to `1` and configure a comma-separated `ROWATCH_TRUSTED_ORIGINS` allowlist (for example `https://app.example.com,https://admin.example.com`)
- use Postgres through `DATABASE_URL`
- replace the dummy payment endpoint with your payment provider
- serve Flask with gunicorn/uwsgi behind a reverse proxy
- configure the Studio plugin `ROWATCH_URL` to the production server
