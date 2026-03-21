"""Auth tests."""

import pytest


def test_login_success(client, admin_token):
    """Test that admin can login."""
    assert admin_token is not None
    assert len(admin_token) > 20


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


def test_me_with_token(client, admin_token):
    """Test /me with valid token."""
    resp = client.get('/api/auth/me', headers={
        'Authorization': f'Bearer {admin_token}'
    })
    assert resp.status_code == 200
    assert resp.json['username'] == 'testadmin'
    assert resp.json['role'] == 'admin'
