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


@pytest.fixture(autouse=True)
def clean_db(app):
    """Clean database between tests."""
    with app.app_context():
        for table in reversed(_db.metadata.sorted_tables):
            _db.session.execute(table.delete())
        _db.session.commit()
    yield


@pytest.fixture
def client(app):
    """Fresh test client per test."""
    return app.test_client()


@pytest.fixture
def auth_client(app):
    """Authenticated test client with fresh session."""
    from app.models.user import User
    from app.extensions import db

    with app.app_context():
        user = User.query.filter_by(username='testadmin').first()
        if not user:
            user = User(username='testadmin', role='admin')
            user.set_password('testpass')
            db.session.add(user)
            db.session.commit()

    c = app.test_client()
    c.post('/api/auth/login', json={
        'username': 'testadmin', 'password': 'testpass'
    })
    return c
