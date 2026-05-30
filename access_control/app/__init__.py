from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from config import Config

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
csrf = CSRFProtect()


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    if not app.config.get('SECRET_KEY'):
        raise RuntimeError(
            "SECRET_KEY is not set. Generate one with "
            "`python -c \"import secrets; print(secrets.token_hex(32))\"` "
            "and set it in the SECRET_KEY environment variable (see .env.example)."
        )

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    # register blueprints
    from app.auth.routes import auth_bp
    from app.routes.main import main_bp
    from app.authorization.routes import authz_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(authz_bp)

    with app.app_context():
        db.create_all()

    return app
