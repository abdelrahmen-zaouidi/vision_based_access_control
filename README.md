# Vision-Based Access Control

Flask web application for role-based facility access control driven by **live facial recognition**. An admin enrols personnel (face image → 128-d encoding stored in DB), defines roles and zones, assigns role↔zone permissions, then triggers camera-based recognition against a chosen zone. Recognised + authorised personnel get a simulated unlock; unknown faces and repeated denials raise alerts and write an immutable audit trail.

> Research / thesis prototype. **Not production-ready** without the follow-ups listed in [AUDIT_REPORT.md](AUDIT_REPORT.md).

## Architecture

```
HTTP request
  → Flask blueprints (auth / main / authorization)
    → Flask-Login session check + Flask-WTF CSRF
      → SQLAlchemy models (Admin, Role, Zone, Personnel, AccessLog, Alert)
      → face_recognition.engine (dlib HOG/CNN locator + 128-d encoding + EMA scoring)
        → CameraManager (background OpenCV capture thread, MJPEG stream)
```

One web process, single SQLite DB (`app.db`). Recognition runs on a background Python thread; the dashboard polls `/recognize/status` for results.

## Features

- Admin login with brute-force protection (Flask-Limiter)
- CSRF-protected forms across the entire admin UI
- Personnel enrolment from a single face image (one face per image enforced)
- Role / zone CRUD + role↔zone assignment matrix
- Live MJPEG camera preview + start/stop recognition controls
- Adaptive recognition pipeline (HOG/CNN locator, EMA per-identity scoring, stability gating)
- Access logs + alerts with searchable tables
- Unknown-face and repeated-denial alerting

## Technology stack

| Layer | |
|---|---|
| Web | Flask 3, Flask-Login, Flask-WTF, Flask-Limiter |
| ORM | Flask-SQLAlchemy 3 + SQLAlchemy 2 |
| Computer vision | OpenCV, `face_recognition` (dlib) |
| Server | gunicorn (production), Werkzeug dev server (local) |
| Storage | SQLite (default); any SQLAlchemy URL works |

## Quickstart

```bash
git clone https://github.com/abdelrahmen-zaouidi/vision_based_access_control.git
cd vision_based_access_control/access_control

python -m venv .venv
.\.venv\Scripts\Activate.ps1        # Windows
# source .venv/bin/activate         # Linux / macOS

pip install -r requirements.txt
cp ../.env.example .env
# edit .env: at minimum, set SECRET_KEY

# Create one admin (one-time):
$env:BOOTSTRAP_ADMIN_USERNAME="admin"
$env:BOOTSTRAP_ADMIN_PASSWORD="<a strong password you choose>"
python run.py --bootstrap-admin

# Start the dev server (binds 127.0.0.1:5000 by default):
python run.py
```

Open http://127.0.0.1:5000 and log in.

### Production (Docker)

```bash
docker build -t vision-access-control .
docker run --rm -p 5000:5000 \
  -e SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')" \
  -e HOST=0.0.0.0 \
  -e SESSION_COOKIE_SECURE=0 \
  --device /dev/video0 \
  vision-access-control
```

`docker-compose up` is also wired (`docker-compose.yml`). For real deployment terminate TLS at a reverse proxy and set `SESSION_COOKIE_SECURE=1` (the default).

## Configuration

All config flows through environment variables. See [.env.example](.env.example).

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `SECRET_KEY` | **yes** | — | Signs Flask session cookies. App refuses to start if unset. |
| `DATABASE_URL` | no | `sqlite:///access_control/app.db` | SQLAlchemy URL. Swap to Postgres for multi-user deployments. |
| `UPLOAD_FOLDER` | no | `<repo>/access_control/uploads` | Where enrolled face images land. |
| `HOST` | no | `127.0.0.1` | Bind address. Use `0.0.0.0` only behind a proxy. |
| `PORT` | no | `5000` | Server port. |
| `SESSION_COOKIE_SECURE` | no | `1` | Set `0` for HTTP-only local dev. |
| `RATELIMIT_STORAGE_URI` | no | `memory://` | Use `redis://...` in production. |
| `BOOTSTRAP_ADMIN_USERNAME` | no | — | Admin to create via `--bootstrap-admin`. |
| `BOOTSTRAP_ADMIN_PASSWORD` | no | — | Password for the above. |

## Project structure

```
.
├── access_control/
│   ├── app/
│   │   ├── __init__.py            # create_app(), extension wiring, security headers
│   │   ├── auth/routes.py         # /login, /logout (rate-limited)
│   │   ├── authorization/routes.py # personnel, roles, zones, alerts, recognition control
│   │   ├── face_recognition/
│   │   │   ├── camera.py          # background OpenCV capture loop, MJPEG stream
│   │   │   └── engine.py          # detection, encoding, decision loop, alerting
│   │   ├── models/models.py       # Admin, Role, Zone, Personnel, AccessLog, Alert
│   │   ├── routes/main.py         # /, /dashboard
│   │   ├── static/                # CSS
│   │   └── templates/             # Jinja templates (all forms CSRF-protected)
│   ├── config.py                  # env-driven Config class
│   ├── requirements.txt           # pinned deps
│   └── run.py                     # entrypoint + --bootstrap-admin
├── .env.example
├── .gitignore
├── AUDIT_REPORT.md                # security audit findings + remediation map
├── Dockerfile
├── docker-compose.yml
├── LICENSE                        # Apache 2.0
├── SECURITY.md
├── CONTRIBUTING.md
└── README.md
```

## Security

See [AUDIT_REPORT.md](AUDIT_REPORT.md) and [SECURITY.md](SECURITY.md). Highlights of what this codebase enforces today:

- `SECRET_KEY` required at startup (no dev fallback)
- CSRF tokens on every POST (Flask-WTF)
- Brute-force-rate-limited `/login` (Flask-Limiter)
- `secure_filename` on uploads (path traversal blocked)
- Session cookies: `HttpOnly`, `SameSite=Lax`, `Secure` by default
- Security headers: `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`
- Face encodings stored as raw `numpy.tobytes` — no `pickle.loads` on DB content
- `.gitignore` covers DB, logs, encodings JSON, uploads

What still needs work (not in this PR — see AUDIT_REPORT.md §5):
- Refactor `engine.py` (544 lines) into testable modules
- Lock `RECOG_STATE` shared mutable state in `authorization/routes.py`
- Add a proper Content-Security-Policy header
- Real unit tests for the decision loop
- Postgres + Redis migration for multi-user deployments

## License

Apache License 2.0 — see [LICENSE](LICENSE).
