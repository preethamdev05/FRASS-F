"""Application configuration."""

import os
from datetime import timedelta

_DEV_FALLBACK_SECRET = 'dev-insecure-fallback-key-do-not-use-in-production'


class Config:
    """Base configuration."""
    SECRET_KEY = os.environ.get('SECRET_KEY', _DEV_FALLBACK_SECRET)
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///attendance.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_size': 10,
        'max_overflow': 20,
    }

    # JWT — RS256-compatible key length
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY', _DEV_FALLBACK_SECRET)
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=1)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)
    JWT_TOKEN_LOCATION = ['headers', 'cookies']
    JWT_COOKIE_SECURE = False
    JWT_COOKIE_CSRF_PROTECT = True
    JWT_CSRF_IN_COOKIES = True
    JWT_ACCESS_COOKIE_NAME = 'access_token'
    JWT_REFRESH_COOKIE_NAME = 'refresh_token'
    JWT_COOKIE_SAMESITE = 'Lax'
    JWT_ACCESS_COOKIE_PATH = '/'
    JWT_REFRESH_COOKIE_PATH = '/api/auth'

    # Rate Limiting — Redis-backed by default, memory fallback
    REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
    RATELIMIT_STORAGE_URI = os.environ.get('RATELIMIT_STORAGE_URI', REDIS_URL)
    RATELIMIT_DEFAULT = '100/minute'

    # File Storage
    FACE_DATA_DIR = os.environ.get('FACE_DATA_DIR', os.path.join(os.path.dirname(os.path.dirname(__file__)), 'face_data'))
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max upload

    # Hardware
    FACE_MODEL = os.environ.get('FACE_MODEL', 'buffalo_l')
    LIVENESS_THRESHOLD = float(os.environ.get('LIVENESS_THRESHOLD', '0.65'))
    RECOGNITION_THRESHOLD = float(os.environ.get('RECOGNITION_THRESHOLD', '0.65'))
    ANTI_SPOOF_MODEL = os.environ.get('ANTI_SPOOF_MODEL', '')  # path to MiniFASNet ONNX

    # Attendance Defaults
    DEFAULT_LATE_THRESHOLD = 10  # minutes
    DEFAULT_GRACE_PERIOD = 5  # minutes

    # CORS
    CORS_ORIGINS = [o.strip() for o in os.environ.get('CORS_ORIGINS', '*').split(',')]

    # Account Lockout
    MAX_LOGIN_ATTEMPTS = int(os.environ.get('MAX_LOGIN_ATTEMPTS', '5'))
    LOCKOUT_DURATION = int(os.environ.get('LOCKOUT_DURATION', '300'))

    # Password Policy
    MIN_PASSWORD_LENGTH = 8

    # Observability
    METRICS_ENABLED = os.environ.get('METRICS_ENABLED', 'true').lower() == 'true'
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
    LOG_FORMAT = os.environ.get('LOG_FORMAT', 'json')  # 'json' or 'text'


class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///attendance.db')
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
    }
    RATELIMIT_STORAGE_URI = 'memory://'
    METRICS_ENABLED = False
    LOG_FORMAT = 'text'


class ProductionConfig(Config):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', '')
    RATELIMIT_STORAGE_URI = os.environ.get('REDIS_URL', 'redis://redis:6379/0')
    JWT_COOKIE_SECURE = True

    @classmethod
    def validate(cls):
        for var in ('SECRET_KEY', 'JWT_SECRET_KEY'):
            val = os.environ.get(var)
            if not val or val == 'change-me-in-production' or val == _DEV_FALLBACK_SECRET:
                raise ValueError(f'{var} must be set to a secure value in production')
        if not os.environ.get('DATABASE_URL'):
            raise ValueError('DATABASE_URL must be set in production')


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    RATELIMIT_ENABLED = False
    RATELIMIT_STORAGE_URI = 'memory://'
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
    }
    LOG_FORMAT = 'text'
    METRICS_ENABLED = False


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig,
}
