"""Attendance API routes."""

import base64
import concurrent.futures
import numpy as np
from datetime import date, datetime, timezone, timedelta

from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.extensions import db, limiter
from app.models.student import Student
from app.models.attendance import AttendanceRecord, AttendanceSession
from app.auth.decorators import role_required
from app.services import attendance as svc

attendance_bp = Blueprint('attendance_api', __name__)

_thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=4)


@attendance_bp.route('/start', methods=['POST'])
@jwt_required()
@role_required('admin', 'teacher')
def start_attendance():
    """Start a new attendance session."""
    identity = get_jwt_identity()
    data = request.json or {}

    session = svc.start_session(
        user_id=int(identity),
        schedule_id=data.get('schedule_id'),
        tolerance=data.get('tolerance', 0.5),
    )

    total = Student.query.filter_by(is_active=True).count()
    return jsonify(session_id=session.id, total_students=total, session=session.to_dict())


@attendance_bp.route('/stop', methods=['POST'])
@jwt_required()
@role_required('admin', 'teacher')
def stop_attendance():
    """Stop the active attendance session."""
    session = svc.get_active_session()
    if session:
        svc.stop_session(session.id)
    return jsonify(status='stopped')


def _process_frame(frame, engine, liveness, session):
    """CPU-heavy ML processing — runs in ThreadPoolExecutor."""
    faces = engine.detect_faces(frame)

    recognized = []
    newly_marked = []

    for face in faces:
        encoding = engine.encode_face(frame, face)
        if encoding is None:
            continue

        bbox = face.bbox.astype(int)
        face_roi = frame[bbox[1]:bbox[3], bbox[0]:bbox[2]]
        landmarks = face.kps if hasattr(face, 'kps') else None
        liveness_result = liveness.analyze(face_roi, landmarks=landmarks)

        student_db_id, confidence = engine.recognize_face(encoding, session.tolerance)

        if student_db_id and liveness_result.is_live:
            student = Student.query.get(student_db_id)
            result = svc.mark_attendance(
                student_db_id=student_db_id,
                session_id=session.id,
                confidence=confidence,
                method='face',
                liveness_score=liveness_result.score,
            )
            entry = {
                'student_id': student_db_id,
                'sid': student.student_id if student else '',
                'name': student.name if student else 'Unknown',
                'confidence': confidence,
                'liveness_score': liveness_result.score,
            }
            recognized.append(entry)
            if result.get('status') == 'marked':
                newly_marked.append(entry)
        elif student_db_id and not liveness_result.is_live:
            recognized.append({
                'student_id': None,
                'sid': '',
                'name': f'Spoof? ({student.name if (student := Student.query.get(student_db_id)) else "Unknown"})',
                'confidence': confidence,
                'liveness_score': liveness_result.score,
                'spoof': True,
                'reason': liveness_result.reason,
            })
        else:
            recognized.append({
                'student_id': None,
                'sid': '',
                'name': 'Unknown',
                'confidence': confidence,
                'liveness_score': liveness_result.score,
            })

    return recognized, newly_marked


@attendance_bp.route('/recognize', methods=['POST'])
@jwt_required()
@role_required('admin', 'teacher')
@limiter.limit('30/minute')
def recognize():
    """Recognize faces in submitted frame and mark attendance."""
    data = request.json
    if not data or not data.get('image'):
        return jsonify(error='image is required'), 400

    session = svc.get_active_session()
    if not session:
        return jsonify(error='No active session'), 400

    image_b64 = data['image']
    try:
        if ',' in image_b64:
            image_b64 = image_b64.split(',')[1]
        else:
            image_b64 = image_b64.strip()
    except (AttributeError, IndexError):
        return jsonify(error='Invalid image format'), 400

    try:
        img_bytes = base64.b64decode(image_b64)
    except Exception:
        return jsonify(error='Invalid base64 image data'), 400

    import cv2
    nparr = np.frombuffer(img_bytes, np.uint8)
    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if frame is None:
        return jsonify(error='Could not decode image'), 400

    from app.services.engine import get_face_engine
    from app.services.liveness import LivenessDetector

    engine = get_face_engine()
    liveness = LivenessDetector(threshold=current_app.config.get('LIVENESS_THRESHOLD', 0.6))

    # Offload CPU-heavy ML to thread pool to avoid blocking the event loop
    future = _thread_pool.submit(_process_frame, frame, engine, liveness, session)
    recognized, newly_marked = future.result(timeout=30)

    total_marked = AttendanceRecord.query.filter_by(session_id=session.id).count()

    return jsonify(
        recognized=recognized,
        newly_marked=newly_marked,
        total_marked=total_marked,
        faces_detected=len(recognized),
    )


@attendance_bp.route('/mark-manual', methods=['POST'])
@jwt_required()
@role_required('admin', 'teacher')
def mark_manual():
    """Manually mark attendance for a student."""
    data = request.json
    if not data or not data.get('student_id'):
        return jsonify(error='student_id is required'), 400

    result = svc.mark_manual(data['student_id'], notes=data.get('notes'))
    if 'error' in result:
        return jsonify(error=result['error']), 400
    return jsonify(result)


@attendance_bp.route('/today', methods=['GET'])
@jwt_required()
def today():
    """Get today's attendance."""
    return jsonify(svc.get_today_attendance())


@attendance_bp.route('/stats', methods=['GET'])
@jwt_required()
def stats():
    """Get attendance statistics."""
    return jsonify(svc.get_today_stats())


@attendance_bp.route('/range', methods=['GET'])
@jwt_required()
def range_query():
    """Get attendance for date range."""
    start = request.args.get('start', date.today().isoformat())
    end = request.args.get('end', date.today().isoformat())
    student_id = request.args.get('student_id', type=int)

    from datetime import date as d
    start_date = d.fromisoformat(start)
    end_date = d.fromisoformat(end)

    records = svc.get_attendance_range(start_date, end_date, student_id)
    return jsonify(records)


@attendance_bp.route('/session', methods=['GET'])
@jwt_required()
def current_session():
    """Get current active session info."""
    session = svc.get_active_session()
    if not session:
        return jsonify(active=False)
    return jsonify(active=True, session=session.to_dict())


@attendance_bp.route('/dashboard', methods=['GET'])
@jwt_required()
def dashboard_data():
    """Get all dashboard data."""
    from app.services.attendance import get_dashboard_data
    return jsonify(get_dashboard_data())
