# Security Policy

## Reporting a vulnerability

Please **do not** open a public GitHub issue for security findings. Instead email **abdelrahmenzaouidi@gmail.com** with:

- A description of the issue
- Steps to reproduce
- The commit hash you tested against
- Optional: a suggested fix

You should expect a first response within 7 days. Coordinated disclosure is appreciated.

## Supported versions

This is a research prototype. Only `main` is maintained; there are no LTS branches.

## What this codebase enforces today

See [AUDIT_REPORT.md](AUDIT_REPORT.md) for the full audit. In short:

- `SECRET_KEY` is required at startup (no fallback).
- All POST endpoints carry a CSRF token (Flask-WTF).
- `/login` is rate-limited (5/min, 20/h per IP).
- Uploaded filenames are passed through `werkzeug.utils.secure_filename`.
- Session cookies: `HttpOnly`, `SameSite=Lax`, `Secure` by default.
- Headers: `X-Frame-Options=DENY`, `X-Content-Type-Options=nosniff`, `Referrer-Policy=same-origin`.
- Face encodings are stored as raw `numpy.tobytes` (no `pickle.loads` on DB content).

## What this codebase does NOT enforce (yet)

Known limitations, documented so you can make informed deployment decisions:

- No Content-Security-Policy header.
- No tests covering the recognition decision loop.
- `RECOG_STATE` global dict in `authorization/routes.py` is not lock-guarded — racy under concurrent recognition triggers.
- No password complexity requirements on admin creation.
- SQLite single-process default — multi-user concurrent deployment requires Postgres + Redis (for rate-limit storage).
- No HTTPS enforcement at the app layer; terminate TLS at a reverse proxy.

## Operating recommendations

- Never expose the dev server (`python run.py`) to the public internet. Use the supplied Dockerfile + a reverse proxy.
- Treat `app.db` as sensitive — it contains admin password hashes, face encodings, and access logs (biometric PII).
- Rotate the bootstrap admin password after first login.
- Keep `.env` out of source control. The shipped `.gitignore` covers this.
