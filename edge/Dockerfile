# ─── IoT Edge Device Docker Build ───
FROM python:3.12-slim-bookworm

WORKDIR /app

# Runtime system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libgomp1 libcamera0 \
    && rm -rf /var/lib/apt/lists/*

# Install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY . .

# Non-root user
RUN useradd -m -s /bin/bash edge && chown -R edge:edge /app
USER edge

# Default config
ENV FRAS_DEVICE_ID=edge-001
ENV FRAS_BACKEND_URL=http://backend:8000
ENV FRAS_CAMERA_DEVICE=0
ENV FRAS_MODEL_TYPE=auto

CMD ["python", "main.py"]
