from flask import Blueprint

authz_bp = Blueprint('authorization', __name__, template_folder='templates', static_folder='static')
