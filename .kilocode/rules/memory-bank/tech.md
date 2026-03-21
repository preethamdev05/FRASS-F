# Technical Context: Xiaomi-FRAS (Face Recognition Attendance System)

## Technology Stack

| Technology | Purpose |
|-----------|---------|
| Python 3.x | Backend language |
| Flask | Web framework |
| Flask-SQLAlchemy | ORM |
| Flask-SocketIO | WebSocket support |
| Flask-Login | Authentication |
| OpenCV / face_recognition | Face recognition |
| SQLite/PostgreSQL | Database |
| Docker | Containerization |
| Gunicorn | WSGI server |
| Jinja2 | Templating |
| JavaScript | Frontend interactivity |

## Development Environment

### Prerequisites

- Python 3.8+
- pip or pipenv
- Docker (optional, for containerized deployment)

### Commands

```bash
pip install -r requirements.txt   # Install dependencies
python -m flask run               # Start dev server
./run.sh                          # Start with script
docker-compose up                 # Start with Docker
pytest tests/                     # Run tests
```

## Project Configuration

### Flask Config (`app/config.py`)
- Database connection settings
- Secret key configuration
- Hardware settings

### Docker (`docker-compose.yml`)
- App service with volume mounts
- Database service
- Environment variable configuration

### Gunicorn (`gunicorn.conf.py`)
- Worker configuration
- Bind address and port

## File Structure

```
/
├── app/                    # Main application
│   ├── api/               # REST API
│   ├── auth/              # Authentication
│   ├── models/            # Database models
│   ├── services/          # Business logic
│   ├── realtime/          # WebSocket events
│   ├── templates/         # HTML templates
│   └── static/            # CSS, JS, assets
├── tests/                 # Test suite
├── migrations/            # Database migrations
├── requirements.txt       # Python dependencies
├── Dockerfile             # Container definition
├── docker-compose.yml     # Multi-container config
├── gunicorn.conf.py       # WSGI server config
├── run.sh / run.bat       # Start scripts
└── .kilocode/             # AI development context
```

## Deployment

### Docker Deployment
```bash
docker-compose up -d
```

### Manual Deployment
```bash
pip install -r requirements.txt
gunicorn -c gunicorn.conf.py app:app
```
