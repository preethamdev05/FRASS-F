"""Authentication routes."""

from flask import Blueprint, request, jsonify, make_response
from flask_jwt_extended import (
    create_access_token, create_refresh_token, jwt_required,
    get_jwt_identity, get_jwt, set_access_cookies, set_refresh_cookies
)
from app.extensions import db, limiter
from app.models.user import User
from app.models.audit import AuditLog
from app.auth.decorators import role_required

auth_bp = Blueprint('auth', __name__)

# Token blacklist (in-memory for dev, Redis for prod)
_token_blacklist = set()


@auth_bp.route('/login', methods=['POST'])
@limiter.limit('5/minute')
def login():
    """Authenticate user and return JWT tokens via HttpOnly cookies."""
    data = request.json
    if not data:
        return jsonify(error='Missing credentials'), 400

    username = data.get('username', '').strip()
    password = data.get('password', '')

    if not username or not password:
        return jsonify(error='Username and password required'), 400

    user = User.query.filter_by(username=username).first()
    if not user or not user.check_password(password):
        return jsonify(error='Invalid credentials'), 401

    if not user.is_active:
        return jsonify(error='Account disabled'), 403

    access_token = create_access_token(identity=str(user.id), additional_claims={'role': user.role})
    refresh_token = create_refresh_token(identity=str(user.id))

    # Audit log
    log = AuditLog(user_id=user.id, action='login', entity_type='user', entity_id=user.id,
                   ip_address=request.remote_addr)
    db.session.add(log)
    db.session.commit()

    resp = make_response(jsonify(user=user.to_dict()))
    set_access_cookies(resp, access_token)
    set_refresh_cookies(resp, refresh_token)
    return resp


@auth_bp.route('/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh():
    """Refresh access token."""
    identity = get_jwt_identity()
    user = User.query.get(int(identity))
    if not user or not user.is_active:
        return jsonify(error='User not found'), 404

    access_token = create_access_token(identity=str(user.id), additional_claims={'role': user.role})
    resp = make_response(jsonify(status='refreshed'))
    set_access_cookies(resp, access_token)
    return resp


@auth_bp.route('/me', methods=['GET'])
@jwt_required()
def me():
    """Get current user info."""
    identity = get_jwt_identity()
    user = User.query.get(int(identity))
    if not user:
        return jsonify(error='User not found'), 404
    return jsonify(user.to_dict())


@auth_bp.route('/logout', methods=['POST'])
@jwt_required()
def logout():
    """Clear JWT cookies."""
    resp = make_response(jsonify(status='logged_out'))
    resp.delete_cookie('access_token')
    resp.delete_cookie('refresh_token')
    return resp


@auth_bp.route('/register', methods=['POST'])
@jwt_required()
@role_required('admin')
def register():
    """Create a new user (admin only)."""
    data = request.json
    if not data:
        return jsonify(error='Missing data'), 400

    username = data.get('username', '').strip()
    password = data.get('password', '')
    email = data.get('email', '').strip() or None
    role = data.get('role', 'teacher')

    if not username or not password:
        return jsonify(error='Username and password required'), 400

    if role not in ('admin', 'teacher', 'student'):
        return jsonify(error='Invalid role'), 400

    if User.query.filter_by(username=username).first():
        return jsonify(error='Username already exists'), 409

    user = User(username=username, email=email, role=role)
    user.set_password(password)

    db.session.add(user)

    # Audit
    identity = get_jwt_identity()
    log = AuditLog(user_id=int(identity), action='create', entity_type='user', entity_id=user.id,
                   details=f'Created user: {username} ({role})', ip_address=request.remote_addr)
    db.session.add(log)
    db.session.commit()

    return jsonify(user.to_dict()), 201


@auth_bp.route('/change-password', methods=['POST'])
@jwt_required()
def change_password():
    """Change own password."""
    identity = get_jwt_identity()
    user = User.query.get(int(identity))
    data = request.json

    old_password = data.get('old_password', '')
    new_password = data.get('new_password', '')

    if not user.check_password(old_password):
        return jsonify(error='Current password incorrect'), 400

    if len(new_password) < 6:
        return jsonify(error='Password must be at least 6 characters'), 400

    user.set_password(new_password)
    db.session.commit()

    return jsonify(status='ok')
