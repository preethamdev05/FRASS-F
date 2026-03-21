"""Schedule API routes."""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from app.extensions import db
from app.models.schedule import Schedule
from app.auth.decorators import role_required

schedules_bp = Blueprint('schedules_api', __name__)


@schedules_bp.route('', methods=['GET'])
@jwt_required()
def list_schedules():
    """List all schedules."""
    schedules = Schedule.query.order_by(Schedule.created_at).all()
    return jsonify([s.to_dict() for s in schedules])


@schedules_bp.route('', methods=['POST'])
@jwt_required()
@role_required('admin')
def create_schedule():
    """Create a new schedule."""
    data = request.json
    if not data:
        return jsonify(error='Missing data'), 400

    name = data.get('name', '').strip()
    start_time = data.get('start_time', '')
    end_time = data.get('end_time', '')
    days = data.get('days_of_week', [])

    if not name or not start_time or not end_time:
        return jsonify(error='name, start_time, and end_time are required'), 400

    schedule = Schedule(
        name=name,
        department=data.get('department'),
        start_time=start_time,
        end_time=end_time,
        late_threshold=data.get('late_threshold', 10),
        grace_period=data.get('grace_period', 5),
    )
    schedule.days_list = days if days else [0, 1, 2, 3]

    db.session.add(schedule)
    db.session.commit()

    return jsonify(schedule.to_dict()), 201


@schedules_bp.route('/<int:sid>', methods=['PUT'])
@jwt_required()
@role_required('admin')
def update_schedule(sid):
    """Update a schedule."""
    schedule = Schedule.query.get(sid)
    if not schedule:
        return jsonify(error='Schedule not found'), 404

    data = request.json
    if 'name' in data:
        schedule.name = data['name'].strip()
    if 'department' in data:
        schedule.department = data['department']
    if 'start_time' in data:
        schedule.start_time = data['start_time']
    if 'end_time' in data:
        schedule.end_time = data['end_time']
    if 'late_threshold' in data:
        schedule.late_threshold = data['late_threshold']
    if 'grace_period' in data:
        schedule.grace_period = data['grace_period']
    if 'days_of_week' in data:
        schedule.days_list = data['days_of_week']
    if 'is_active' in data:
        schedule.is_active = bool(data['is_active'])

    db.session.commit()
    return jsonify(schedule.to_dict())


@schedules_bp.route('/<int:sid>', methods=['DELETE'])
@jwt_required()
@role_required('admin')
def delete_schedule(sid):
    """Delete a schedule."""
    schedule = Schedule.query.get(sid)
    if not schedule:
        return jsonify(error='Schedule not found'), 404

    db.session.delete(schedule)
    db.session.commit()
    return jsonify(status='deleted')
