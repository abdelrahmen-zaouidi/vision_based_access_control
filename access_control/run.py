from app import create_app, db
from app.models.models import Admin
from werkzeug.security import generate_password_hash

app = create_app()


def ensure_admin():
    with app.app_context():
        if db.session.query(Admin).count() == 0:
            username = 'admin'
            password = 'adminpass'
            admin = Admin(username=username)
            admin.set_password(password)
            db.session.add(admin)
            db.session.commit()
            print('Created default admin -> username: admin password: adminpass')


if __name__ == '__main__':
    ensure_admin()
    app.run(host='0.0.0.0', port=5000, debug=True)
