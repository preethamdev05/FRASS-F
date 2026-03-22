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
    """Authenticated test client with CSRF token support."""
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

    # Login — stores JWT cookies and CSRF cookies
    resp = c.post('/api/auth/login', json={
        'username': 'testadmin', 'password': 'testpass'
    })
    assert resp.status_code == 200, f'Login failed: {resp.json}'

    # Extract CSRF token from cookies and wrap client to auto-send it
    csrf_token = None
    for cookie_header in resp.headers.getlist('Set-Cookie'):
        if 'csrf_access_token' in cookie_header:
            # Parse: csrf_access_token=VALUE; ...
            for part in cookie_header.split(';'):
                part = part.strip()
                if part.startswith('csrf_access_token='):
                    csrf_token = part.split('=', 1)[1]
                    break

    if csrf_token:
        original_post = c.post
        original_get = c.get
        original_put = c.put
        original_delete = c.delete

        def _inject_csrf(method, url, **kwargs):
            headers = kwargs.pop('headers', {}) or {}
            headers['X-CSRF-TOKEN'] = csrf_token
            return method(url, headers=headers, **kwargs)

        c.post = lambda url, **kw: _inject_csrf(original_post, url, **kw)
        c.get = lambda url, **kw: _inject_csrf(original_get, url, **kw)
        c.put = lambda url, **kw: _inject_csrf(original_put, url, **kw)
        c.delete = lambda url, **kw: _inject_csrf(original_delete, url, **kw)

    return c
