"""Application configuration."""

import os
from datetime import timedelta


class Config:
    """Base configuration."""
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-change-in-production')
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///attendance.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_size': 10,
        'max_overflow': 20,
    }

    # JWT
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY', 'jwt-secret-change-in-production')
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=1)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)
    JWT_TOKEN_LOCATION = ['headers', 'cookies']
    JWT_COOKIE_SECURE = False  # True in production with HTTPS

    # Rate Limiting
    RATELIMIT_STORAGE_URI = os.environ.get('REDIS_URL', 'memory://')
    RATELIMIT_DEFAULT = '100/minute'

    # File Storage
    FACE_DATA_DIR = os.environ.get('FACE_DATA_DIR', os.path.join(os.path.dirname(os.path.dirname(__file__)), 'face_data'))
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max upload

    # Redis
    REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')

    # Hardware
    FACE_MODEL = os.environ.get('FACE_MODEL', 'buffalo_l')
    LIVENESS_THRESHOLD = float(os.environ.get('LIVENESS_THRESHOLD', '0.6'))

    # Attendance Defaults
    DEFAULT_LATE_THRESHOLD = 10  # minutes
    DEFAULT_GRACE_PERIOD = 5  # minutes

    # CORS
    CORS_ORIGINS = os.environ.get('CORS_ORIGINS', '*').split(',')


class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///attendance.db')
    RATELIMIT_STORAGE_URI = 'memory://'


class ProductionConfig(Config):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    RATELIMIT_STORAGE_URI = os.environ.get('REDIS_URL', 'redis://redis:6379/0')
    JWT_COOKIE_SECURE = True


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig,
}
