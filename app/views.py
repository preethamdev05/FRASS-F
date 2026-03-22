"""HTML view routes (Jinja2 templates)."""

from flask import Blueprint, render_template, redirect
from flask_jwt_extended import verify_jwt_in_request

views_bp = Blueprint('views', __name__)


@views_bp.route('/')
def index():
    return redirect('/dashboard')


@views_bp.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')


@views_bp.route('/login')
def login():
    return render_template('auth/login.html')


@views_bp.route('/register')
def register():
    return render_template('register.html')


def _login_redirect_if_unauth():
    """Redirect to login page if no valid JWT is present."""
    try:
        verify_jwt_in_request()
    except Exception:
        return redirect('/login')
    return None


@views_bp.route('/attendance')
def attendance():
    resp = _login_redirect_if_unauth()
    if resp:
        return resp
    return render_template('attendance.html')


@views_bp.route('/students')
def students():
    resp = _login_redirect_if_unauth()
    if resp:
        return resp
    return render_template('students.html')


@views_bp.route('/reports')
def reports():
    resp = _login_redirect_if_unauth()
    if resp:
        return resp
    return render_template('reports.html')


@views_bp.route('/schedules')
def schedules():
    resp = _login_redirect_if_unauth()
    if resp:
        return resp
    return render_template('schedules.html')


@views_bp.route('/admin')
def admin_panel():
    resp = _login_redirect_if_unauth()
    if resp:
        return resp
    return render_template('admin/panel.html')
