# ─── Face Attendance System — Production Docker Build ───
FROM python:3.12-slim AS builder

WORKDIR /build

# System deps for building C extensions (psycopg2, numpy, opencv)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python packages to a prefix
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ─── Runtime stage ───
FROM python:3.12-slim AS runtime

WORKDIR /app

# Runtime system deps only (no build tools)
# Package names for Debian Bookworm (python:3.12-slim)
# NOTE: libgdk-pixbuf was renamed from 2.0-0 to -2.0-0 in Bookworm
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libcairo2 \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

# Verify Python packages are accessible
RUN python -c "import flask; print('Flask', flask.__version__)"

# App code
COPY . .

# Create non-root user
RUN useradd -m -s /bin/bash appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:5000/api/health || exit 1

CMD ["gunicorn", "--config", "gunicorn.conf.py", "app:create_app()"]
