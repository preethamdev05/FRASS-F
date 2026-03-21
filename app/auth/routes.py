"""Authentication routes — Production-grade with MFA and Redis-backed lockout."""

import io
import re
import time
import logging
from flask import Blueprint, request, jsonify, make_response
from flask_jwt_extended import (
    create_access_token, create_refresh_token, jwt_required,
    get_jwt_identity, set_access_cookies, set_refresh_cookies, get_jwt
)
from app.extensions import db, limiter, get_redis
from app.models.user import User
from app.models.audit import AuditLog
from app.auth.decorators import role_required

logger = logging.getLogger(__name__)

auth_bp = Blueprint('auth', __name__)

MIN_PASSWORD_LENGTH = 8
PASSWORD_PATTERN = re.compile(r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).+$')


def _validate_password_strength(password: str) -> str | None:
    """Validate password strength. Returns error message or None."""
    if len(password) < MIN_PASSWORD_LENGTH:
        return f'Password must be at least {MIN_PASSWORD_LENGTH} characters'
    if not PASSWORD_PATTERN.match(password):
        return 'Password must contain uppercase, lowercase, and a digit'
    return None


def _check_lockout_redis(username: str) -> str | None:
    """Check account lockout via Redis (cross-worker safe)."""
    r = get_redis()
    if not r:
        return None  # Fallback: no Redis, use model-level lockout
    try:
        key = f'login_lockout:{username}'
        data = r.hgetall(key)
        if data and int(data.get('attempts', 0)) >= 5:
            ttl = r.ttl(key)
            if ttl > 0:
                return f'Account locked. Try again in {ttl} seconds.'
    except Exception:
        pass
    return None


def _record_failed_redis(username: str):
    """Record failed login attempt in Redis."""
    r = get_redis()
    if not r:
        return
    try:
        key = f'login_lockout:{username}'
        pipe = r.pipeline()
        pipe.hincrby(key, 'attempts', 1)
        pipe.hset(key, 'last_attempt', str(time.time()))
        # Set TTL on first attempt
        if not r.exists(key):
            pipe.expire(key, 300)  # 5 minutes
        pipe.execute()
    except Exception:
        pass


def _clear_lockout_redis(username: str):
    """Clear lockout data on successful login."""
    r = get_redis()
    if not r:
        return
    try:
        r.delete(f'login_lockout:{username}')
    except Exception:
        pass


def _is_token_revoked(jti: str) -> bool:
    """Check if JWT token has been revoked."""
    r = get_redis()
    if not r:
        return False
    try:
        return r.exists(f'revoked_token:{jti}')
    except Exception:
        return False


def _revoke_token(jti: str, expires_in: int = 3600):
    """Revoke a JWT token."""
    r = get_redis()
    if not r:
        return
    try:
        r.setex(f'revoked_token:{jti}', expires_in, '1')
    except Exception:
        pass


@auth_bp.route('/login', methods=['POST'])
@limiter.limit('10/minute')
def login():
    """Authenticate user with optional MFA verification."""
    data = request.json
    if not data:
        return jsonify(error='Missing credentials'), 400

    username = data.get('username', '').strip()
    password = data.get('password', '')
    mfa_code = data.get('mfa_code')

    if not username or not password:
        return jsonify(error='Username and password required'), 400

    # Check Redis lockout first (cross-worker safe)
    lockout_msg = _check_lockout_redis(username)
    if lockout_msg:
        return jsonify(error=lockout_msg), 429

    user = User.query.filter_by(username=username).first()
    if not user or not user.check_password(password):
        # Record failure in both Redis and model
        _record_failed_redis(username)
        if user:
            user.record_failed_login()
        return jsonify(error='Invalid credentials'), 401

    # Check model-level lockout (DB-backed)
    if user.is_locked():
        from datetime import timezone
        remaining = int((user.locked_until - datetime.now(timezone.utc)).total_seconds())
        return jsonify(error=f'Account locked. Try again in {max(remaining, 1)} seconds.'), 429

    if not user.is_active:
        return jsonify(error='Account disabled'), 403

    # MFA verification
    if user.mfa_enabled:
        if not mfa_code:
            return jsonify(error='MFA code required', mfa_required=True), 401
        import pyotp
        totp = pyotp.TOTP(user.mfa_secret)
        if not totp.verify(mfa_code, valid_window=1):
            return jsonify(error='Invalid MFA code'), 401

    user.record_successful_login()
    _clear_lockout_redis(username)

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
    """Clear JWT cookies and revoke token."""
    jwt_data = get_jwt()
    jti = jwt_data.get('jti')
    if jti:
        exp = jwt_data.get('exp', 0)
        remaining = max(0, int(exp - time.time()))
        _revoke_token(jti, remaining)

    resp = make_response(jsonify(status='logged_out'))
    resp.delete_cookie('access_token', path='/')
    resp.delete_cookie('refresh_token', path='/api/auth')
    return resp


@auth_bp.route('/mfa/setup', methods=['POST'])
@jwt_required()
def mfa_setup():
    """Enable MFA for the current user. Returns QR code URI."""
    identity = get_jwt_identity()
    user = User.query.get(int(identity))
    if not user:
        return jsonify(error='User not found'), 404

    import pyotp
    import qrcode
    import base64

    # Generate secret
    secret = pyotp.random_base32()
    user.mfa_secret = secret
    db.session.commit()

    # Generate provisioning URI
    totp = pyotp.TOTP(secret)
    uri = totp.provisioning_uri(name=user.username, issuer_name='FaceAttend')

    # Generate QR code as base64 PNG
    qr = qrcode.make(uri)
    buf = io.BytesIO()
    qr.save(buf, format='PNG')
    qr_b64 = base64.b64encode(buf.getvalue()).decode()

    return jsonify(
        secret=secret,
        provisioning_uri=uri,
        qr_code=f'data:image/png;base64,{qr_b64}',
    )


@auth_bp.route('/mfa/verify', methods=['POST'])
@jwt_required()
def mfa_verify():
    """Verify MFA code and enable MFA."""
    identity = get_jwt_identity()
    user = User.query.get(int(identity))
    data = request.json

    code = data.get('code', '') if data else ''
    if not user or not user.mfa_secret:
        return jsonify(error='MFA not set up'), 400

    import pyotp
    totp = pyotp.TOTP(user.mfa_secret)
    if totp.verify(code, valid_window=1):
        user.mfa_enabled = True
        db.session.commit()
        return jsonify(status='MFA enabled')
    return jsonify(error='Invalid code'), 400


@auth_bp.route('/mfa/disable', methods=['POST'])
@jwt_required()
def mfa_disable():
    """Disable MFA for the current user (requires password confirmation)."""
    identity = get_jwt_identity()
    user = User.query.get(int(identity))
    data = request.json

    password = data.get('password', '') if data else ''
    if not user.check_password(password):
        return jsonify(error='Password incorrect'), 400

    user.mfa_enabled = False
    user.mfa_secret = None
    db.session.commit()
    return jsonify(status='MFA disabled')


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

    pw_error = _validate_password_strength(password)
    if pw_error:
        return jsonify(error=pw_error), 400

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

    pw_error = _validate_password_strength(new_password)
    if pw_error:
        return jsonify(error=pw_error), 400

    user.set_password(new_password)
    db.session.commit()

    return jsonify(status='ok')
