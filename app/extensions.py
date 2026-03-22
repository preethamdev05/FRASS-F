"""Flask extensions initialization."""

import logging
from typing import Optional
import redis as redis_lib
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager
from flask_socketio import SocketIO
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

logger = logging.getLogger(__name__)


def _rate_limit_key():
    """Use JWT identity for per-user rate limiting; fall back to IP."""
    try:
        from flask_jwt_extended import get_jwt_identity
        uid = get_jwt_identity()
        if uid:
            return f'user:{uid}'
    except Exception:
        pass
    return get_remote_address()


def _detect_async_mode():
    """Auto-detect SocketIO async mode based on available libraries."""
    try:
        import gevent  # noqa: F401
        return 'gevent'
    except ImportError:
        pass
    try:
        import eventlet  # noqa: F401
        return 'eventlet'
    except ImportError:
        pass
    return 'threading'


db = SQLAlchemy()
migrate = Migrate()
jwt = JWTManager()
socketio = SocketIO(cors_allowed_origins='*', async_mode=_detect_async_mode())
limiter = Limiter(key_func=_rate_limit_key, default_limits=['100/minute'])

# Redis client — initialized lazily in create_app
redis_client: Optional[redis_lib.Redis] = None


def get_redis() -> Optional[redis_lib.Redis]:
    """Get the Redis client instance, or None if unavailable."""
    return redis_client


def init_redis(app):
    """Initialize Redis connection from app config."""
    global redis_client
    try:
        redis_client = redis_lib.from_url(
            app.config['REDIS_URL'],
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
            retry_on_timeout=True,
        )
        redis_client.ping()
        app.logger.info('Redis connected: %s', app.config['REDIS_URL'])
    except Exception as e:
        app.logger.warning('Redis unavailable (%s), falling back to in-memory', e)
        redis_client = None


def close_redis(app):
    """Close the Redis connection if it exists."""
    global redis_client
    if redis_client is not None:
        try:
            redis_client.close()
            app.logger.info('Redis connection closed')
        except Exception as e:
            app.logger.warning('Error closing Redis connection: %s', e)
        redis_client = None
