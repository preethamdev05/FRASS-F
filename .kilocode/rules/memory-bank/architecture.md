# System Patterns: Xiaomi-FRAS (Face Recognition Attendance System)

## Architecture Overview

```
app/
├── __init__.py              # Flask app factory
├── config.py                # Configuration
├── extensions.py            # Flask extensions
├── views.py                 # Main views
├── api/                     # REST API endpoints
│   ├── admin.py             # Admin API
│   ├── attendance.py        # Attendance API
│   ├── reports.py           # Reports API
│   ├── schedules.py         # Schedules API
│   └── students.py          # Students API
├── auth/                    # Authentication
│   ├── decorators.py        # Auth decorators
│   └── routes.py            # Auth routes
├── models/                  # Database models
│   ├── attendance.py        # Attendance model
│   ├── audit.py             # Audit log model
│   ├── face.py              # Face data model
│   ├── schedule.py          # Schedule model
│   ├── student.py           # Student model
│   └── user.py              # User model
├── services/                # Business logic
│   ├── attendance.py        # Attendance service
│   ├── engine.py            # Main engine
│   ├── export.py            # Export service
│   ├── face_engine.py       # Face recognition engine
│   ├── hardware.py          # Hardware integration
│   ├── liveness.py          # Liveness detection
│   ├── notification.py      # Notifications
│   └── seed.py              # Data seeding
├── realtime/                # WebSocket events
│   └── events.py            # Socket events
├── templates/               # Jinja2 templates
│   ├── base.html            # Base template
│   ├── dashboard.html       # Dashboard
│   ├── attendance.html      # Attendance view
│   ├── students.html        # Students list
│   ├── register.html        # Registration
│   ├── reports.html         # Reports
│   ├── schedules.html       # Schedules
│   └── admin/panel.html     # Admin panel
└── static/                  # Static assets
    ├── css/style.css        # Styles
    ├── js/app.js            # Main JS
    ├── js/realtime.js       # WebSocket JS
    ├── manifest.json        # PWA manifest
    └── sw.js                # Service worker
```

## Key Design Patterns

### 1. Flask Application Factory
Uses the Flask application factory pattern for flexible configuration and testing.

### 2. Service Layer Pattern
Business logic is separated into service modules for clear separation of concerns.

### 3. Blueprint Pattern
API routes are organized using Flask blueprints.

### 4. Real-time Communication
WebSocket integration via Flask-SocketIO for live attendance updates.

### 5. Hardware Abstraction
Hardware services abstract camera and sensor integration.

## Testing Structure

```
tests/
├── conftest.py              # Test fixtures
├── test_attendance.py       # Attendance tests
├── test_auth.py             # Auth tests
├── test_hardware.py         # Hardware tests
├── test_liveness.py         # Liveness tests
└── test_students.py         # Student tests
```

## Deployment

- Docker + Docker Compose for containerized deployment
- Gunicorn as WSGI server
- Nginx recommended for production reverse proxy
