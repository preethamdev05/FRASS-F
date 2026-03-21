.PHONY: dev test lint migrate seed docker-up docker-down clean

dev:
	FLASK_ENV=development python3 -c "from app import create_app; create_app().run(host='0.0.0.0', port=5000, debug=True)"

test:
	pytest tests/ -v --tb=short --cov=app --cov-report=term-missing

lint:
	ruff check app/ tests/
	mypy app/ --ignore-missing-imports || true

format:
	ruff format app/ tests/

migrate:
	flask db migrate -m "$(msg)"
	flask db upgrade

seed:
	python3 -c "from app import create_app; app = create_app(); app.app_context().push(); from app.services.seed import seed_defaults; seed_defaults()"

docker-up:
	docker compose up -d --build

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f app

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete 2>/dev/null || true
	rm -rf .pytest_cache htmlcov .coverage .mypy_cache 2>/dev/null || true
