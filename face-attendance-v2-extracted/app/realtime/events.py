"""WebSocket event handlers and broadcast helpers."""

import logging
from flask_socketio import emit, join_room, leave_room
from app.extensions import socketio

logger = logging.getLogger(__name__)


@socketio.on('connect')
def handle_connect():
    """Client connected."""
    join_room('dashboard')
    logger.debug('Client connected to WebSocket')


@socketio.on('disconnect')
def handle_disconnect():
    """Client disconnected."""
    logger.debug('Client disconnected from WebSocket')


@socketio.on('join_session')
def handle_join_session(data):
    """Join a live attendance session room."""
    session_id = data.get('session_id')
    if session_id:
        join_room(f'session_{session_id}')
        logger.debug(f'Client joined session room: {session_id}')


@socketio.on('leave_session')
def handle_leave_session(data):
    """Leave a session room."""
    session_id = data.get('session_id')
    if session_id:
        leave_room(f'session_{session_id}')


def broadcast_student_marked(session_id: int, data: dict):
    """Broadcast that a student was marked present."""
    socketio.emit('student_marked', data, room=f'session_{session_id}')
    socketio.emit('student_marked', data, room='dashboard')


def broadcast_face_recognized(session_id: int, data: dict):
    """Broadcast face recognition event."""
    socketio.emit('face_recognized', data, room=f'session_{session_id}')


def broadcast_spoof_detected(session_id: int, data: dict):
    """Broadcast spoof detection alert."""
    socketio.emit('spoof_detected', data, room=f'session_{session_id}')


def broadcast_stats_update(stats: dict):
    """Broadcast updated stats to dashboard."""
    socketio.emit('stats_update', stats, room='dashboard')
