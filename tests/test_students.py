"""Student API tests."""


def test_list_students_empty(auth_client):
    """Test empty student list."""
    resp = auth_client.get('/api/students')
    assert resp.status_code == 200
    assert resp.json == []


def test_create_student(auth_client):
    """Test creating a student."""
    resp = auth_client.post('/api/students', json={
        'student_id': 'TEST001',
        'name': 'Test Student',
        'department': 'CS',
    })
    assert resp.status_code == 201
    assert resp.json['name'] == 'Test Student'
    assert resp.json['student_id'] == 'TEST001'


def test_create_duplicate_student(auth_client):
    """Test duplicate student ID."""
    auth_client.post('/api/students', json={
        'student_id': 'DUP001', 'name': 'First'
    })

    resp = auth_client.post('/api/students', json={
        'student_id': 'DUP001', 'name': 'Second'
    })
    assert resp.status_code == 409


def test_create_student_missing_fields(auth_client):
    """Test creating student without required fields."""
    resp = auth_client.post('/api/students', json={
        'email': 'test@test.com'
    })
    assert resp.status_code == 400
