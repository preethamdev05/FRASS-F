"""Auth decorators and JWT handlers."""

from functools import wraps
from flask import jsonify
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
from app.models.user import User


def role_required(*roles):
    """Decorator that restricts access to specific roles."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            verify_jwt_in_request()
            identity = get_jwt_identity()
            from app.extensions import db
            user = db.session.get(User, int(identity))
            if not user or user.role not in roles:
                return jsonify(error='Insufficient permissions'), 403
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def get_current_user():
    """Get the current authenticated user."""
    identity = get_jwt_identity()
    if identity:
        from app.extensions import db
        return db.session.get(User, int(identity))
    return None


def register_jwt_handlers(app):
    """Register JWT error handlers."""

    @app.errorhandler(404)
    def not_found(e):
        return jsonify(error='Not found'), 404

    @app.errorhandler(500)
    def internal_error(e):
        return jsonify(error='Internal server error'), 500
