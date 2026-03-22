"""Flask application factory — Production-grade."""

import os
import sys
import logging
from flask import Flask, jsonify, g, request
from flask_cors import CORS
from dotenv import load_dotenv

from app.config import config
from app.extensions import db, migrate, jwt, socketio, limiter, init_redis

load_dotenv()


def _setup_logging(app):
    """Configure structured logging (JSON for production, text for dev)."""
    log_level = getattr(logging, app.config.get('LOG_LEVEL', 'INFO').upper(), logging.INFO)
    log_format = app.config.get('LOG_FORMAT', 'text')

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)

    if log_format == 'json':
        formatter = logging.Formatter(
            '{"timestamp":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","message":"%(message)s"}',
        )
    else:
        formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s')

    handler.setFormatter(formatter)
    root_logger.addHandler(handler)

    # Quieten noisy loggers
    logging.getLogger('werkzeug').setLevel(logging.WARNING)
    logging.getLogger('engineio').setLevel(logging.WARNING)


def _setup_metrics(app):
    """Configure Prometheus metrics instrumentation."""
    if not app.config.get('METRICS_ENABLED', True):
        return

    try:
        from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

        request_counter = Counter(
            'fras_requests_total', 'Total HTTP requests',
            ['method', 'endpoint', 'status'],
        )
        Histogram(
            'fras_request_duration_seconds', 'Request duration in seconds',
            ['method', 'endpoint'],
        )

        @app.after_request
        def _record_metrics(response):
            if request.endpoint and request.endpoint != 'health_check':
                try:
                    request_counter.labels(
                        method=request.method,
                        endpoint=request.endpoint,
                        status=response.status_code,
                    ).inc()
                except Exception:
                    pass
            return response

        @app.route('/api/metrics')
        def metrics():
            from flask import Response
            return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)

        app.logger.info('Prometheus metrics enabled at /api/metrics')
    except ImportError:
        app.logger.info('prometheus_client not installed, metrics disabled')


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

    # Setup logging first so subsequent init messages are structured
    _setup_logging(app)
    logger = logging.getLogger(__name__)

    # Ensure face data directory exists
    os.makedirs(app.config['FACE_DATA_DIR'], exist_ok=True)

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    socketio.init_app(app)
    limiter.init_app(app)

    # Redis (graceful fallback if unavailable)
    init_redis(app)

    # Prometheus metrics
    _setup_metrics(app)

    # CORS for API endpoints
    CORS(app, resources={r"/api/*": {
        "origins": app.config.get('CORS_ORIGINS', ['*']),
        "supports_credentials": True,
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"],
    }})

    # Request timing middleware
    @app.before_request
    def _start_timer():
        g.request_start_time = __import__('time').time()

    # Security headers middleware
    @app.after_request
    def _set_security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['Permissions-Policy'] = 'camera=(self), microphone=()'
        if app.config.get('JWT_COOKIE_SECURE'):
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        return response

    # Health check endpoint (no auth — for cloud load balancers)
    @app.route('/api/health')
    def health_check():
        """Cloud health check — verifies DB and Redis connectivity."""
        checks = {}

        # Database check
        try:
            db.session.execute(db.text('SELECT 1'))
            checks['database'] = 'ok'
        except Exception as e:
            checks['database'] = f'error: {str(e)}'

        # Redis check
        try:
            from app.extensions import get_redis
            r = get_redis()
            if r:
                r.ping()
                checks['redis'] = 'ok'
            else:
                checks['redis'] = 'unavailable'
        except Exception:
            checks['redis'] = 'error'

        # Only database is critical — Redis is optional (app falls back to in-memory)
        db_ok = checks.get('database') == 'ok'
        return jsonify(
            status='healthy' if db_ok else 'degraded',
            checks=checks,
            version='2.0.0',
        ), 200 if db_ok else 503

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

    logger.info('App created with config: %s', config_name)
    return app
