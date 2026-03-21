"""Auth tests."""


def test_login_success(client, auth_client):
    """Test that admin can login (auth_client is already logged in)."""
    resp = client.get('/api/auth/me')
    # auth_client has cookies, but client doesn't — so this should 401
    assert resp.status_code == 401

    # auth_client has cookies — this should 200
    resp = auth_client.get('/api/auth/me')
    assert resp.status_code == 200
    assert resp.json['username'] == 'testadmin'
    assert resp.json['role'] == 'admin'


def test_login_fail(client):
    """Test login with wrong credentials."""
    resp = client.post('/api/auth/login', json={
        'username': 'nobody', 'password': 'wrong'
    })
    assert resp.status_code == 401


def test_me_requires_auth(client):
    """Test /me without token."""
    resp = client.get('/api/auth/me')
    assert resp.status_code == 401


def test_me_with_token(auth_client):
    """Test /me with valid cookie."""
    resp = auth_client.get('/api/auth/me')
    assert resp.status_code == 200
    assert resp.json['username'] == 'testadmin'
    assert resp.json['role'] == 'admin'
