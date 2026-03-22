"""Student API routes."""

import re
import os
import base64
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.extensions import db
from app.models.student import Student
from app.models.face import FaceEncoding
from app.models.audit import AuditLog
from app.auth.decorators import role_required

students_bp = Blueprint('students_api', __name__)


def _sanitize_student_id(sid):
    """Only allow alphanumeric, dash, underscore."""
    if not sid:
        return None
    sid = str(sid).strip()
    if re.match(r'^[a-zA-Z0-9_-]+$', sid):
        return sid
    return None


@students_bp.route('', methods=['GET'])
@jwt_required()
def list_students():
    """List all students."""
    students = Student.query.order_by(Student.created_at.desc()).all()
    return jsonify([s.to_dict() for s in students])


@students_bp.route('', methods=['POST'])
@jwt_required()
@role_required('admin', 'teacher')
def create_student():
    """Create a new student."""
    data = request.json
    if not data:
        return jsonify(error='Missing data'), 400

    sid = _sanitize_student_id(data.get('student_id'))
    name = data.get('name', '').strip()

    if not sid or not name:
        return jsonify(error='student_id and name are required'), 400

    if Student.query.filter_by(student_id=sid).first():
        return jsonify(error='Student ID already exists'), 409

    student = Student(
        student_id=sid,
        name=name,
        email=data.get('email'),
        department=data.get('department'),
        semester=data.get('semester'),
    )
    db.session.add(student)

    # Audit
    identity = get_jwt_identity()
    log = AuditLog(user_id=int(identity), action='create', entity_type='student',
                   entity_id=student.id, ip_address=request.remote_addr)
    db.session.add(log)
    db.session.commit()

    return jsonify(student.to_dict()), 201


@students_bp.route('/<int:sid>', methods=['GET'])
@jwt_required()
def get_student(sid):
    """Get a student."""
    student = db.session.get(Student, sid)
    if not student:
        return jsonify(error='Student not found'), 404
    return jsonify(student.to_dict())


@students_bp.route('/<int:sid>', methods=['PUT'])
@jwt_required()
@role_required('admin', 'teacher')
def update_student(sid):
    """Update a student."""
    student = db.session.get(Student, sid)
    if not student:
        return jsonify(error='Student not found'), 404

    data = request.json
    if data.get('name'):
        student.name = data['name'].strip()
    if 'email' in data:
        student.email = data['email']
    if 'department' in data:
        student.department = data['department']
    if 'semester' in data:
        student.semester = data['semester']
    if 'is_active' in data:
        student.is_active = bool(data['is_active'])

    db.session.commit()
    return jsonify(student.to_dict())


@students_bp.route('/<int:sid>', methods=['DELETE'])
@jwt_required()
@role_required('admin')
def delete_student(sid):
    """Delete a student and all associated data."""
    student = db.session.get(Student, sid)
    if not student:
        return jsonify(error='Student not found'), 404

    # Delete face encodings from DB
    from app.services.engine import get_face_engine
    get_face_engine().delete_student_encodings(sid)

    # Delete images via storage service
    from app.services.storage import StorageService
    storage = StorageService(current_app.config['FACE_DATA_DIR'])
    storage.delete_student_dir(student.student_id)

    # Audit
    identity = get_jwt_identity()
    log = AuditLog(user_id=int(identity), action='delete', entity_type='student',
                   entity_id=sid, details=f'Deleted: {student.name}',
                   ip_address=request.remote_addr)
    db.session.add(log)

    db.session.delete(student)
    db.session.commit()

    return jsonify(status='deleted')


@students_bp.route('/register-face', methods=['POST'])
@jwt_required()
@role_required('admin', 'teacher')
def register_face():
    """Register a face encoding for a student."""
    data = request.json
    if not data:
        return jsonify(error='Missing data'), 400

    student_db_id = data.get('student_id')
    image_b64 = data.get('image')

    if not student_db_id or not image_b64:
        return jsonify(error='student_id and image are required'), 400

    student = db.session.get(Student, student_db_id)
    if not student:
        return jsonify(error='Student not found'), 404

    # Decode base64 image
    try:
        if ',' in image_b64:
            image_b64 = image_b64.split(',')[1]
        img_bytes = base64.b64decode(image_b64)
    except Exception:
        return jsonify(error='Invalid image data'), 400

    # Encode face
    from app.services.engine import get_face_engine
    engine = get_face_engine()
    encoding, msg = engine.encode_face_from_image(img_bytes)

    if encoding is None:
        return jsonify(error=msg), 400

    # Save image to disk via storage service
    import cv2
    import numpy as np
    nparr = np.frombuffer(img_bytes, np.uint8)
    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    photo_index = student.photo_count + 1
    from app.services.storage import StorageService
    storage = StorageService(current_app.config['FACE_DATA_DIR'])
    student_dir = storage.ensure_dir(student.student_id)
    photo_path = os.path.join(student_dir, f'photo_{photo_index}.jpg')
    cv2.imwrite(photo_path, frame)

    # Save encoding
    engine.save_encoding(student_db_id, encoding, photo_path)

    # Save to DB using safe serialization (numpy.tobytes — no pickle)
    from app.services.face_engine import _serialize_single_encoding
    face_enc = FaceEncoding(
        student_id=student_db_id,
        encoding_blob=_serialize_single_encoding(encoding),
        photo_path=photo_path,
    )
    db.session.add(face_enc)

    student.photo_count = photo_index
    db.session.commit()

    return jsonify(
        status='ok',
        message=f'Face #{photo_index} registered',
        photo_count=student.photo_count,
    )
