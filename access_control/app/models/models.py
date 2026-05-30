from app import db, login_manager
from flask_login import UserMixin
from datetime import datetime
import pickle
from werkzeug.security import generate_password_hash, check_password_hash


role_zone = db.Table('role_zone_access',
    db.Column('role_id', db.Integer, db.ForeignKey('roles.id'), primary_key=True),
    db.Column('zone_id', db.Integer, db.ForeignKey('zones.id'), primary_key=True)
)


class Admin(UserMixin, db.Model):
    __tablename__ = 'admins'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


@login_manager.user_loader
def load_user(user_id):
    return Admin.query.get(int(user_id))


class Role(db.Model):
    __tablename__ = 'roles'
    id = db.Column(db.Integer, primary_key=True)
    role_name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.String(255))
    personnel = db.relationship('Personnel', backref='role', lazy=True)
    zones = db.relationship('Zone', secondary=role_zone, back_populates='roles')


class Zone(db.Model):
    __tablename__ = 'zones'
    id = db.Column(db.Integer, primary_key=True)
    zone_name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.String(255))
    roles = db.relationship('Role', secondary=role_zone, back_populates='zones')


class Personnel(db.Model):
    __tablename__ = 'personnel'
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(200), nullable=False)
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id'))
    face_encoding = db.Column(db.LargeBinary)
    active = db.Column(db.Boolean, default=True)

    def set_encoding(self, encoding_array):
        self.face_encoding = pickle.dumps(encoding_array)

    def get_encoding(self):
        if not self.face_encoding:
            return None
        return pickle.loads(self.face_encoding)


class AccessLog(db.Model):
    __tablename__ = 'access_logs'
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(200))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    zone = db.Column(db.String(100))
    status = db.Column(db.String(20))  # success / failure
    denial_reason = db.Column(db.String(255))
    action_taken = db.Column(db.String(255))


class Alert(db.Model):
    __tablename__ = 'alerts'
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    zone = db.Column(db.String(100))
    alert_type = db.Column(db.String(100))
    description = db.Column(db.String(500))
    resolved = db.Column(db.Boolean, default=False)
