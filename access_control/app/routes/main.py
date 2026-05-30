from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required

main_bp = Blueprint('main', __name__, template_folder='templates')


@main_bp.route('/')
def index():
    return redirect(url_for('auth.login'))


@main_bp.route('/admin')
@login_required
def admin_index():
    return redirect(url_for('authorization.dashboard'))


@main_bp.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')
