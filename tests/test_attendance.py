"""Attendance API tests."""


def test_today_empty(auth_client):
    """Test today's attendance when empty."""
    resp = auth_client.get('/api/attendance/today')
    assert resp.status_code == 200
    assert resp.json == []


def test_mark_manual(auth_client):
    """Test manual attendance marking."""
    # Create a student first
    s = auth_client.post('/api/students', json={
        'student_id': 'M001', 'name': 'Manual Test'
    })
    sid = s.json['id']

    # Mark attendance
    resp = auth_client.post('/api/attendance/mark-manual', json={
        'student_id': sid
    })
    assert resp.status_code == 200
    assert resp.json['status'] == 'marked'


def test_mark_duplicate_manual(auth_client):
    """Test marking same student twice."""
    s = auth_client.post('/api/students', json={
        'student_id': 'M002', 'name': 'Dup Test'
    })
    sid = s.json['id']

    auth_client.post('/api/attendance/mark-manual', json={
        'student_id': sid
    })

    resp = auth_client.post('/api/attendance/mark-manual', json={
        'student_id': sid
    })
    assert resp.status_code == 400


def test_start_session(auth_client):
    """Test starting an attendance session."""
    resp = auth_client.post('/api/attendance/start', json={
        'tolerance': 0.5
    })
    assert resp.status_code == 200
    assert 'session_id' in resp.json


def test_attendance_stats(auth_client):
    """Test attendance stats."""
    resp = auth_client.get('/api/attendance/stats')
    assert resp.status_code == 200
    assert 'total_students' in resp.json
