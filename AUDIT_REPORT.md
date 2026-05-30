# Repository Audit Report — vision_based_access_control

**Auditor:** senior-engineer security & quality review
**Date:** 2026-05-30
**Repo:** https://github.com/abdelrahmen-zaouidi/vision_based_access_control
**Pre-audit commit:** `58c8ac1` (HEAD of `main` before this PR; full history was rewritten by squash into a single orphan commit per the maintainer's decision; the present PR sits on top of that clean baseline)

---

## 1. Project Overview

A Flask web application that performs face-recognition-based **role-based access control** for a simulated secure facility. Admin logs in, enrolls personnel (full name + face image → 128-d face encoding stored in DB), defines roles/zones, assigns role↔zone permissions, then triggers live camera recognition against a chosen zone. Recognized + authorized personnel get a simulated unlock; unknown faces and repeated denials raise alerts and write audit logs.

**Stack:** Flask · Flask-Login · Flask-SQLAlchemy · OpenCV · `face_recognition` (dlib) · Werkzeug · gunicorn (declared, not actually used).

## 2. Architecture Summary

```
HTTP request
  → Flask blueprints (auth / main / authorization)
    → Flask-Login session check
      → SQLAlchemy models (Admin, Role, Zone, Personnel, AccessLog, Alert)
      → face_recognition.engine (dlib HOG/CNN locator + 128-d encoding + EMA scoring)
        → CameraManager (background OpenCV capture thread, MJPEG stream)
```

- One web process, single SQLite DB (`app.db`).
- Recognition runs in a background Python thread; status polled via `/recognize/status`.

## 3. Pre-audit Health Score

| Dimension | Score (0–10) |
|---|---|
| Security | 2 |
| Maintainability | 4 |
| Professionalism | 1 |
| Documentation | 1 |
| Deployment readiness | 2 |
| Scalability | 3 |
| Reliability | 4 |
| Code quality | 4 |

**Overall: 2.6 / 10.**

## 4. Risk Findings (pre-fix)

### 🔴 CRITICAL

**C1. Sensitive data recoverable from git history.**
The 10 most recent commits were `Delete X` but no `git filter-repo` ever ran. Anyone with a clone could recover:
- `access_control/app.db` (~48 KB SQLite) — admin password hash, personnel records, **face encodings**, access logs.
- `access_control/face_recog.log` (~124 KB) — face match logs with names, timestamps, zones (biometric PII).
- `access_control/tools/encodings_report.json` — pairwise distance matrix + person name.
**Resolution (this PR):** the full history was nuked and replaced with a single orphan baseline commit before this PR was opened. **Treat any credentials/data that ever lived in the old history as permanently compromised** — anyone who cloned before the rewrite still has copies. The leaked admin password (`adminpass`) is removed from code by Commit 3.

**C2. CSRF protection entirely missing.**
No `Flask-WTF`, no manual tokens. Every POST is forgeable by any page a logged-in admin visits: `/login`, `/personnel/add|edit|delete/...`, `/roles/...`, `/zones/...`, `/role_zone`, `/access_logs/delete/...`, `/alerts/delete/...`, `/simulate/recognize`, `/recognize/start|stop`. **Resolution:** Commit 5 adds `Flask-WTF CSRFProtect` and `csrf_token()` in every form.

**C3. Hardcoded default admin `admin/adminpass` auto-created on first run.**
`run.py:ensure_admin()` creates this admin and prints credentials. Deployed-and-forgotten installations are immediately pwnable. **Resolution:** Commit 3 removes auto-creation. Bootstrap admin via `--bootstrap-admin` CLI flag reading `BOOTSTRAP_ADMIN_USERNAME` / `BOOTSTRAP_ADMIN_PASSWORD` env vars, intended for one-time use.

**C4. `Flask` `debug=True` + `host=0.0.0.0`** in `run.py`.
Werkzeug debug console grants code execution if PIN cracked. Binding to all interfaces exposes it on LAN. **Resolution:** Commit 3 reads `HOST` / `PORT` from env (defaults `127.0.0.1:5000`) and never enables debug.

### 🟠 HIGH

**H1. Path traversal in upload** (`engine.py:enroll_person_image`). Raw `file.filename` is concatenated into a path without `secure_filename()`. **Resolution:** Commit 6.

**H2. `Flask SECRET_KEY` defaults to `'dev-secret-key'`.** Session forgery trivial. **Resolution:** Commit 2 requires the env var and raises at startup if unset.

**H3. `pickle.loads` on DB content** (`Personnel.get_encoding()`). If the DB is ever tampered (SQLi elsewhere, file tamper, future bug), arbitrary code execution. **Resolution:** Commit 8 stores face encodings via `numpy.tobytes()` / `numpy.frombuffer()` (no pickle).

**H4. No brute-force protection on `/login`.** **Resolution:** Commit 7 adds `Flask-Limiter` with `5 per minute` on `/login`.

**H5. No session-cookie security flags.** **Resolution:** Commit 7 sets `SESSION_COOKIE_HTTPONLY=True`, `SESSION_COOKIE_SAMESITE='Lax'`, `SESSION_COOKIE_SECURE` env-controlled (default `True` when not in DEBUG).

### 🟡 MEDIUM

**M1.** No `.gitignore` → cause of the original `app.db`/log leak. **Resolution:** Commit 1.
**M2.** No CSRF tokens in templates. **Resolution:** Commit 5.
**M3.** No CORS, no CSP, no security headers. **Resolution:** Commit 7 adds the basics (X-Frame-Options: DENY, X-Content-Type-Options: nosniff, Referrer-Policy: same-origin).
**M4.** Threading-safety smells in `RECOG_STATE` global (mutation without lock). **Not fixed** in this PR — would require refactor of `routes.py` recognition control endpoints. Tracked in **Recommended Next Steps**.
**M5.** Hardcoded Windows upload path `C:\Users\Administrator\app\uploads`. **Resolution:** Commit 2 makes it env-driven with a portable default.
**M6.** Opaque LargeBinary `face_encoding` column. Partially addressed by Commit 8.
**M7.** No tests, no CI, no linting. **Resolution:** Commit 11 adds a minimal GitHub Actions workflow (ruff lint + smoke import test). Adding actual test coverage is in Recommended Next Steps.

### 🟢 LOW

**L1.** No `LICENSE`. **Resolution:** Commit 10 (Apache 2.0).
**L2.** No proper README. **Resolution:** Commit 9.
**L3.** No type hints. Not addressed (large surface; would need its own PR).
**L4.** No Dockerfile. **Resolution:** Commit 12.
**L5.** No `SECURITY.md` / `CONTRIBUTING.md`. **Resolution:** Commit 13.

## 5. What this PR does NOT do (intentionally)

- Does **not** refactor `engine.py` (544 lines, no tests). Splitting it is high-value long-term but risk-bearing without a test harness. Recommended as a follow-up PR.
- Does **not** add a fix for `RECOG_STATE` race conditions. Same reason.
- Does **not** add a database migration script. The pickle→numpy change in Commit 8 is backward-incompatible for any existing `app.db` with enrolled personnel. The migration path: re-enroll personnel after upgrade, or write a one-off conversion script.

## 6. Recommended Next Steps

1. **Re-enroll any existing personnel** after deploying this PR (the encoding storage format changed).
2. **Rotate any credentials** that ever lived in the original git history (treat all prior `app.db` content as compromised).
3. Add unit tests for `engine._run_recognition_core` decision branches.
4. Refactor `engine.py` into `preprocess.py` / `detector.py` / `decision_loop.py` once tests exist.
5. Replace the `RECOG_STATE` global dict with a proper lock or `threading.Event`-based handoff.
6. Add a CSP header tuned to the actual JS/CSS the dashboard loads.
7. Consider migrating from SQLite to Postgres for any multi-user/concurrent deployment.

## 7. Commits in this PR

| # | Commit | Phase |
|---|---|---|
| 1 | `chore(repo): add .gitignore, .env.example, AUDIT_REPORT.md` | repo hygiene |
| 2 | `security(config): require SECRET_KEY env, portable upload dir` | C4, H2, M5 |
| 3 | `security(run): remove default admin, disable debug, env-driven host/port` | C3, C4 |
| 4 | `chore(deps): pin requirements + add Flask-WTF + Flask-Limiter` | enables C2, H4 |
| 5 | `security(csrf): add CSRFProtect and tokens in all templates` | C2, M2 |
| 6 | `security(upload): secure_filename + portable paths` | H1 |
| 7 | `security(auth): rate-limit /login + session cookie flags + headers` | H4, H5, M3 |
| 8 | `refactor(models): replace pickle with numpy serialization` | H3 |
| 9 | `docs(readme): professional README` | L2 |
| 10 | `chore(license): Apache 2.0 LICENSE` | L1 |
| 11 | `chore(ci): GitHub Actions for lint + smoke test` | M7 |
| 12 | `chore(docker): Dockerfile + docker-compose` | L4 |
| 13 | `docs: SECURITY.md + CONTRIBUTING.md` | L5 |
