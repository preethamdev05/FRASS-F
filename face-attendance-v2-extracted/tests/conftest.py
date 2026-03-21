"""Test fixtures."""

import pytest
from app import create_app
from app.extensions import db as _db


@pytest.fixture(scope='session')
def app():
    """Create application for testing."""
    app = create_app('testing')
    with app.app_context():
        _db.create_all()
        yield app
        _db.drop_all()


@pytest.fixture(scope='function')
def db(app):
    """Database fixture."""
    with app.app_context():
        _db.create_all()
        yield _db
        _db.session.rollback()
        _db.drop_all()


@pytest.fixture
def client(app):
    """Test client."""
    return app.test_client()


@pytest.fixture
def admin_token(client):
    """Get admin JWT token."""
    from app.models.user import User
    from app.extensions import db

    with client.application.app_context():
        user = User(username='testadmin', role='admin')
        user.set_password('testpass')
        db.session.add(user)
        db.session.commit()

    resp = client.post('/api/auth/login', json={
        'username': 'testadmin', 'password': 'testpass'
    })
    return resp.json['access_token']
