from flask import Blueprint

face_bp = Blueprint('face', __name__, template_folder='templates', static_folder='static')
