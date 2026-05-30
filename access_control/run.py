"""Application entrypoint.

Run modes:
  python run.py                         # start the dev server (env-driven host/port, debug off)
  python run.py --bootstrap-admin       # create one admin from BOOTSTRAP_ADMIN_{USERNAME,PASSWORD}
                                        # env vars, then exit. Use once per fresh deployment.

In production prefer a real WSGI server (gunicorn/waitress) over this script.
"""
import argparse
import os
import sys

from app import create_app, db
from app.models.models import Admin


def bootstrap_admin(app):
    username = os.environ.get('BOOTSTRAP_ADMIN_USERNAME')
    password = os.environ.get('BOOTSTRAP_ADMIN_PASSWORD')
    if not username or not password:
        print(
            'BOOTSTRAP_ADMIN_USERNAME and BOOTSTRAP_ADMIN_PASSWORD must both be set.',
            file=sys.stderr,
        )
        return 2
    with app.app_context():
        if db.session.query(Admin).filter_by(username=username).first():
            print(f'Admin {username!r} already exists; nothing to do.')
            return 0
        admin = Admin(username=username)
        admin.set_password(password)
        db.session.add(admin)
        db.session.commit()
        print(f'Created admin {username!r}.')
        return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description='Vision-based access control')
    parser.add_argument(
        '--bootstrap-admin',
        action='store_true',
        help='Create an admin from BOOTSTRAP_ADMIN_{USERNAME,PASSWORD} env vars, then exit.',
    )
    args = parser.parse_args(argv)

    app = create_app()

    if args.bootstrap_admin:
        return bootstrap_admin(app)

    host = os.environ.get('HOST', '127.0.0.1')
    port = int(os.environ.get('PORT', '5000'))
    app.run(host=host, port=port, debug=False)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
