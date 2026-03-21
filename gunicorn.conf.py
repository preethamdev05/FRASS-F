"""Gunicorn production config."""

import multiprocessing
import os

# Bind
bind = os.environ.get('GUNICORN_BIND', '0.0.0.0:5000')

# Workers — 2-4 for face recognition (memory intensive)
workers = int(os.environ.get('GUNICORN_WORKERS', min(4, multiprocessing.cpu_count())))
worker_class = 'gevent'

# Timeouts
timeout = 120
graceful_timeout = 30
keepalive = 5

# Logging
accesslog = '-'
errorlog = '-'
loglevel = os.environ.get('GUNICORN_LOG_LEVEL', 'info')

# Process naming
proc_name = 'face-attendance'

# Preload app for faster worker startup
preload_app = True
