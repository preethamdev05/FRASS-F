"""Flask extensions initialization."""

import logging
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


db = SQLAlchemy()
migrate = Migrate()
jwt = JWTManager()
socketio = SocketIO(cors_allowed_origins='*', async_mode='gevent')
limiter = Limiter(key_func=_rate_limit_key, default_limits=['100/minute'])

# Redis client — initialized lazily in create_app
redis_client: redis_lib.Redis | None = None


def get_redis() -> redis_lib.Redis | None:
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
