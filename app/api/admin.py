"""Admin API routes."""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.extensions import db
from app.models.user import User
from app.models.audit import AuditLog
from app.auth.decorators import role_required
from app.services.hardware import get_hardware_profile

admin_bp = Blueprint('admin_api', __name__)


@admin_bp.route('/users', methods=['GET'])
@jwt_required()
@role_required('admin')
def list_users():
    """List all users."""
    users = User.query.order_by(User.created_at.desc()).all()
    return jsonify([u.to_dict() for u in users])


@admin_bp.route('/users/<int:uid>', methods=['PUT'])
@jwt_required()
@role_required('admin')
def update_user(uid):
    """Update a user (admin only)."""
    user = db.session.get(User, uid)
    if not user:
        return jsonify(error='User not found'), 404

    data = request.json
    if 'role' in data and data['role'] in ('admin', 'teacher', 'student'):
        user.role = data['role']
    if 'is_active' in data:
        user.is_active = bool(data['is_active'])
    if 'email' in data:
        user.email = data['email']

    db.session.commit()
    return jsonify(user.to_dict())


@admin_bp.route('/users/<int:uid>', methods=['DELETE'])
@jwt_required()
@role_required('admin')
def delete_user(uid):
    """Delete a user."""
    identity = int(get_jwt_identity())
    if uid == identity:
        return jsonify(error='Cannot delete your own account'), 400

    user = db.session.get(User, uid)
    if not user:
        return jsonify(error='User not found'), 404

    try:
        db.session.delete(user)
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify(error='Cannot delete user: related records exist'), 409
    return jsonify(status='deleted')


@admin_bp.route('/audit', methods=['GET'])
@jwt_required()
@role_required('admin')
def audit_log():
    """Get audit log entries."""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    action = request.args.get('action')
    user_id = request.args.get('user_id', type=int)

    query = AuditLog.query.order_by(AuditLog.created_at.desc())

    if action:
        query = query.filter_by(action=action)
    if user_id:
        query = query.filter_by(user_id=user_id)

    total = query.count()
    logs = query.offset((page - 1) * per_page).limit(per_page).all()

    return jsonify(
        total=total,
        page=page,
        per_page=per_page,
        entries=[entry.to_dict() for entry in logs],
    )


@admin_bp.route('/hardware', methods=['GET'])
@jwt_required()
@role_required('admin')
def hardware_info():
    """Get hardware detection info."""
    profile = get_hardware_profile()
    return jsonify(profile.to_dict())
