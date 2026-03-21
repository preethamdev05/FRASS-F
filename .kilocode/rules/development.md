# Development Rules

## Critical Rules

- **Language**: Python 3.x with Flask
- **Package manager**: Use `pip install -r requirements.txt`
- **Never run** `flask run` - the sandbox handles this automatically
- **Always commit and push** after completing changes:
  ```bash
  pytest tests/ && git add -A && git commit -m "descriptive message" && git push
  ```

## Commands

| Command | Purpose |
|---------|---------|
| `pip install -r requirements.txt` | Install dependencies |
| `pytest tests/` | Run test suite |
| `python -m flask run` | Start dev server (local only) |
| `docker-compose up` | Start with Docker |

## Best Practices

### Flask/Python
- Use the application factory pattern
- Separate business logic into services
- Use blueprints for API organization
- Follow PEP 8 style guidelines
- Use type hints where appropriate

### API Routes
- Return proper HTTP status codes
- Use Flask's `jsonify` for JSON responses
- Handle errors gracefully with try/except
- Include appropriate error messages

### Database
- Use SQLAlchemy models
- Run migrations for schema changes
- Use proper relationships and indexes

### Code Quality
- Run `pytest tests/` before committing
- Write descriptive commit messages
- Follow Python naming conventions

### Deployment
- Use Docker for consistent environments
- Use Gunicorn for production WSGI server
- Configure environment variables properly
