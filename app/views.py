"""HTML view routes (Jinja2 templates)."""

from flask import Blueprint, render_template, redirect

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


@views_bp.route('/attendance')
def attendance():
    return render_template('attendance.html')


@views_bp.route('/students')
def students():
    return render_template('students.html')


@views_bp.route('/reports')
def reports():
    return render_template('reports.html')


@views_bp.route('/schedules')
def schedules():
    return render_template('schedules.html')


@views_bp.route('/admin')
def admin_panel():
    return render_template('admin/panel.html')
