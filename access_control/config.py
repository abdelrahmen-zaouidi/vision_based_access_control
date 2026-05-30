"""Application configuration.

All runtime config flows through environment variables. The only hard
requirement is SECRET_KEY: the app refuses to start without one
(see create_app() in app/__init__.py).
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# Upload directory: env override, otherwise repo-local default. Must be writable.
UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', str(BASE_DIR / 'uploads'))
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


class Config:
    # No fallback: missing SECRET_KEY must fail loudly at startup, not silently
    # sign sessions with a publicly known string.
    SECRET_KEY = os.environ.get('SECRET_KEY')

    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL',
        f'sqlite:///{(BASE_DIR / "app.db").as_posix()}',
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    UPLOAD_FOLDER = UPLOAD_FOLDER
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
