"""Student API tests."""


def test_list_students_empty(client, admin_token):
    """Test empty student list."""
    resp = client.get('/api/students', headers={
        'Authorization': f'Bearer {admin_token}'
    })
    assert resp.status_code == 200
    assert resp.json == []


def test_create_student(client, admin_token):
    """Test creating a student."""
    resp = client.post('/api/students', json={
        'student_id': 'TEST001',
        'name': 'Test Student',
        'department': 'CS',
    }, headers={'Authorization': f'Bearer {admin_token}'})
    assert resp.status_code == 201
    assert resp.json['name'] == 'Test Student'
    assert resp.json['student_id'] == 'TEST001'


def test_create_duplicate_student(client, admin_token):
    """Test duplicate student ID."""
    headers = {'Authorization': f'Bearer {admin_token}'}
    client.post('/api/students', json={
        'student_id': 'DUP001', 'name': 'First'
    }, headers=headers)

    resp = client.post('/api/students', json={
        'student_id': 'DUP001', 'name': 'Second'
    }, headers=headers)
    assert resp.status_code == 409


def test_create_student_missing_fields(client, admin_token):
    """Test creating student without required fields."""
    resp = client.post('/api/students', json={
        'email': 'test@test.com'
    }, headers={'Authorization': f'Bearer {admin_token}'})
    assert resp.status_code == 400
