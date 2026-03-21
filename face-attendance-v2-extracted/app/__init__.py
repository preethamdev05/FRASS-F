"""Flask application factory."""

import os
import logging
from flask import Flask
from dotenv import load_dotenv

from app.config import config
from app.extensions import db, migrate, jwt, socketio, limiter

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger(__name__)


def create_app(config_name=None):
    """Create and configure the Flask application."""
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'development')

    app = Flask(
        __name__,
        template_folder='templates',
        static_folder='static',
    )
    app.config.from_object(config[config_name])

    # Ensure face data directory exists
    os.makedirs(app.config['FACE_DATA_DIR'], exist_ok=True)

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    socketio.init_app(app)
    limiter.init_app(app)

    # Import all models so Alembic sees them
    from app.models import user, student, face, attendance, schedule, audit  # noqa: F401

    # Register blueprints
    from app.auth.routes import auth_bp
    from app.api.students import students_bp
    from app.api.attendance import attendance_bp
    from app.api.schedules import schedules_bp
    from app.api.reports import reports_bp
    from app.api.admin import admin_bp
    from app.views import views_bp

    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(students_bp, url_prefix='/api/students')
    app.register_blueprint(attendance_bp, url_prefix='/api/attendance')
    app.register_blueprint(schedules_bp, url_prefix='/api/schedules')
    app.register_blueprint(reports_bp, url_prefix='/api/reports')
    app.register_blueprint(admin_bp, url_prefix='/api/admin')
    app.register_blueprint(views_bp)

    # Register WebSocket events
    from app.realtime import events  # noqa: F401

    # JWT error handlers
    from app.auth.decorators import register_jwt_handlers
    register_jwt_handlers(app)

    # Create tables on first run (dev mode — production uses Alembic)
    with app.app_context():
        if config_name == 'development':
            db.create_all()
            from app.services.seed import seed_defaults
            seed_defaults()

    logger.info(f'App created with config: {config_name}')
    return app
