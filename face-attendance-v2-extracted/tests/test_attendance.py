"""Attendance API tests."""


def test_today_empty(client, admin_token):
    """Test today's attendance when empty."""
    resp = client.get('/api/attendance/today', headers={
        'Authorization': f'Bearer {admin_token}'
    })
    assert resp.status_code == 200
    assert resp.json == []


def test_mark_manual(client, admin_token):
    """Test manual attendance marking."""
    headers = {'Authorization': f'Bearer {admin_token}'}

    # Create a student first
    s = client.post('/api/students', json={
        'student_id': 'M001', 'name': 'Manual Test'
    }, headers=headers)
    sid = s.json['id']

    # Mark attendance
    resp = client.post('/api/attendance/mark-manual', json={
        'student_id': sid
    }, headers=headers)
    assert resp.status_code == 200
    assert resp.json['status'] == 'marked'


def test_mark_duplicate_manual(client, admin_token):
    """Test marking same student twice."""
    headers = {'Authorization': f'Bearer {admin_token}'}

    s = client.post('/api/students', json={
        'student_id': 'M002', 'name': 'Dup Test'
    }, headers=headers)
    sid = s.json['id']

    client.post('/api/attendance/mark-manual', json={
        'student_id': sid
    }, headers=headers)

    resp = client.post('/api/attendance/mark-manual', json={
        'student_id': sid
    }, headers=headers)
    assert resp.status_code == 400


def test_start_session(client, admin_token):
    """Test starting an attendance session."""
    resp = client.post('/api/attendance/start', json={
        'tolerance': 0.5
    }, headers={'Authorization': f'Bearer {admin_token}'})
    assert resp.status_code == 200
    assert 'session_id' in resp.json


def test_attendance_stats(client, admin_token):
    """Test attendance stats."""
    resp = client.get('/api/attendance/stats', headers={
        'Authorization': f'Bearer {admin_token}'
    })
    assert resp.status_code == 200
    assert 'total_students' in resp.json
