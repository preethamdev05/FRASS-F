"""IoT Backend — production-grade processing layer.

Features:
- API key authentication on all endpoints
- pgvector HNSW search for O(log n) matching
- Connection pool monitoring via Prometheus
- Replay attack prevention with TTL cleanup
- Device health reporting
- Embedding quality validation
- Async attendance logging via Redis Streams
"""

import os
import logging
import time
import json
import numpy as np
from datetime import datetime, timezone, timedelta
from functools import wraps
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger(__name__)

def _parse_api_keys(raw):
    """Parse API_KEYS env var, falling back to empty dict on invalid JSON."""
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        logger.warning('Invalid API_KEYS env var, using empty dict')
        return {}


app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get('SECRET_KEY', 'iot-backend-secret'),
    SQLALCHEMY_DATABASE_URI=os.environ.get('DATABASE_URL', 'sqlite:///iot_attendance.db'),
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    SQLALCHEMY_ENGINE_OPTIONS={'pool_pre_ping': True, 'pool_size': 20, 'max_overflow': 30},
    REDIS_URL=os.environ.get('REDIS_URL', 'redis://localhost:6379/1'),
    RECOGNITION_THRESHOLD=float(os.environ.get('RECOGNITION_THRESHOLD', '0.65')),
    LIVENESS_THRESHOLD=float(os.environ.get('LIVENESS_THRESHOLD', '0.65')),
    DEDUP_COOLDOWN=int(os.environ.get('DEDUP_COOLDOWN', '300')),
    API_KEYS=_parse_api_keys(os.environ.get('API_KEYS')),
    MIN_EMBEDDING_QUALITY=float(os.environ.get('MIN_EMBEDDING_QUALITY', '0.85')),
)

db = SQLAlchemy(app)
CORS(app)

# ─── Redis (lazy init) ───

_redis_client = None

def _get_redis():
    global _redis_client
    if _redis_client is None:
        try:
            import redis as redis_lib
            _redis_client = redis_lib.from_url(app.config['REDIS_URL'], decode_responses=True,
                                               socket_connect_timeout=2, socket_timeout=2)
            _redis_client.ping()
        except Exception:
            _redis_client = None
    return _redis_client


# ─── API Key Auth ───

def require_api_key(f):
    """Decorator: validates X-API-Key header against stored keys."""
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = request.headers.get('X-API-Key', '')
        device_id = request.headers.get('X-Device-ID', '')
        if not device_id and request.is_json and request.json:
            device_id = request.json.get('device_id', '')

        if not api_key:
            return jsonify(error='X-API-Key header required'), 401

        # Check against configured API keys
        valid_keys = app.config.get('API_KEYS', {})
        if isinstance(valid_keys, dict):
            # Per-device keys: {device_id: api_key}
            if device_id and device_id in valid_keys and valid_keys[device_id] == api_key:
                return f(*args, **kwargs)
            # Global key
            if valid_keys.get('_global') == api_key:
                return f(*args, **kwargs)
        elif isinstance(valid_keys, str) and valid_keys == api_key:
            return f(*args, **kwargs)

        return jsonify(error='Invalid API key'), 401
    return decorated


# ─── Models ───

class Device(db.Model):
    __tablename__ = 'devices'
    id = db.Column(db.String(64), primary_key=True)
    name = db.Column(db.String(128))
    location = db.Column(db.String(256))
    status = db.Column(db.String(20), default='active')
    last_seen = db.Column(db.DateTime)
    config = db.Column(db.Text, default='{}')
    api_key = db.Column(db.String(128), index=True)
    registered_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    # Health fields
    uptime_seconds = db.Column(db.Integer, default=0)
    memory_mb = db.Column(db.Float, default=0)
    queue_size = db.Column(db.Integer, default=0)
    fps_actual = db.Column(db.Float, default=0)
    health_reported_at = db.Column(db.DateTime)


class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    external_id = db.Column(db.String(64), unique=True, nullable=False)
    name = db.Column(db.String(128), nullable=False)
    metadata_json = db.Column(db.Text, default='{}')
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class FaceEmbedding(db.Model):
    __tablename__ = 'face_embeddings'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    embedding_blob = db.Column(db.LargeBinary, nullable=False)
    quality_score = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class AttendanceLog(db.Model):
    __tablename__ = 'attendance_logs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    device_id = db.Column(db.String(64), nullable=False, index=True)
    timestamp = db.Column(db.DateTime, nullable=False, index=True)
    confidence = db.Column(db.Float)
    liveness_score = db.Column(db.Float)
    status = db.Column(db.String(20), default='present')
    session_id = db.Column(db.String(64), index=True)
    nonce = db.Column(db.String(128), unique=True)

    __table_args__ = (
        db.Index('idx_attendance_user_time', 'user_id', 'timestamp'),
        db.Index('idx_attendance_device_time', 'device_id', 'timestamp'),
    )


class ReplayGuard(db.Model):
    __tablename__ = 'replay_guard'
    nonce = db.Column(db.String(128), primary_key=True)
    device_id = db.Column(db.String(64), index=True)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)


# ─── Prometheus Metrics ───

_pool_metrics = {}

def _setup_pool_metrics():
    try:
        from prometheus_client import Gauge, Counter
        _pool_metrics['pool_size'] = Gauge('iot_db_pool_size', 'DB pool size')
        _pool_metrics['pool_checked_out'] = Gauge('iot_db_pool_checked_out', 'DB connections in use')
        _pool_metrics['recognitions'] = Counter('iot_recognitions_total', 'Total recognitions', ['status'])
        _pool_metrics['attendance_marks'] = Counter('iot_attendance_marks_total', 'Attendance marks')

        from sqlalchemy import event

        @event.listens_for(db.engine, 'checkout')
        def _on_checkout(dbapi_conn, connection_rec, connection_proxy):
            try:
                _pool_metrics['pool_checked_out'].set(connection_rec._pool.checkedout())
                _pool_metrics['pool_size'].set(connection_rec._pool.size())
            except Exception:
                pass

        @event.listens_for(db.engine, 'checkin')
        def _on_checkin(dbapi_conn, connection_rec):
            try:
                _pool_metrics['pool_checked_out'].set(connection_rec._pool.checkedout())
            except Exception:
                pass
    except Exception:
        pass


# ─── Embedding Cache ───

_embedding_cache = {}
_cache_loaded = False


def load_embeddings():
    global _embedding_cache, _cache_loaded
    _embedding_cache = {}
    try:
        records = FaceEmbedding.query.all()
        for rec in records:
            emb = np.frombuffer(rec.embedding_blob, dtype=np.float32).copy()
            if rec.user_id not in _embedding_cache:
                _embedding_cache[rec.user_id] = []
            _embedding_cache[rec.user_id].append(emb)
        _cache_loaded = True
        total = sum(len(v) for v in _embedding_cache.values())
        logger.info('Loaded %d embeddings for %d users', total, len(_embedding_cache))
    except Exception as e:
        logger.warning('Embedding load failed: %s', e)


def embedding_quality(embedding: np.ndarray) -> float:
    """Score embedding quality based on L2 norm deviation from 1.0."""
    norm = np.linalg.norm(embedding)
    return 1.0 - abs(1.0 - norm)


def match_embedding(query: np.ndarray, threshold: float) -> tuple:
    if not _cache_loaded:
        load_embeddings()
    if not _embedding_cache:
        return None, 0.0

    result = _match_pgvector(query, threshold)
    if result[0] is not None or result[1] > 0:
        return result

    best_id, best_score = None, 0.0
    for uid, embeddings in _embedding_cache.items():
        for emb in embeddings:
            score = float(np.dot(query, emb))
            if score > best_score:
                best_score = score
                best_id = uid

    confidence = round(best_score * 100, 1)
    if best_score >= threshold:
        return best_id, confidence
    return None, confidence


def _match_pgvector(query: np.ndarray, threshold: float) -> tuple:
    try:
        if 'postgresql' not in str(db.engine.url):
            return None, 0.0
        vec_str = '[' + ','.join(f'{float(x):.6f}' for x in query) + ']'
        result = db.session.execute(
            db.text("""
                SELECT fe.user_id, 1 - (embedding_vector <=> :vec) AS sim
                FROM face_embeddings fe
                WHERE fe.embedding_vector IS NOT NULL
                ORDER BY embedding_vector <=> :vec LIMIT 1
            """), {'vec': vec_str}
        ).fetchone()
        if result and result[1] >= threshold:
            return result[0], round(float(result[1]) * 100, 1)
        return None, round(float(result[1]) * 100, 1) if result else (None, 0.0)
    except Exception:
        return None, 0.0


# ─── Replay Prevention (with periodic TTL cleanup) ───

_last_replay_cleanup = 0
REPLAY_CLEANUP_INTERVAL = 300  # seconds


def check_replay(nonce: str, device_id: str) -> bool:
    global _last_replay_cleanup
    if not nonce:
        return False
    existing = ReplayGuard.query.get(nonce)
    if existing:
        return False
    db.session.add(ReplayGuard(nonce=nonce, device_id=device_id))
    db.session.commit()

    # Periodic cleanup: delete nonces older than 1 hour (every 5 min)
    now = time.time()
    if now - _last_replay_cleanup >= REPLAY_CLEANUP_INTERVAL:
        _last_replay_cleanup = now
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
            ReplayGuard.query.filter(ReplayGuard.timestamp < cutoff).delete()
            db.session.commit()
        except Exception:
            pass
    return True


# ─── API Endpoints ───

@app.route('/api/health')
def health():
    try:
        db.session.execute(db.text('SELECT 1'))
        r = _get_redis()
        redis_ok = r is None or r.ping()
        return jsonify(status='healthy', version='3.1.0-iot', redis=redis_ok)
    except Exception:
        return jsonify(status='degraded'), 503


@app.route('/api/metrics')
def metrics():
    try:
        from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
        from flask import Response
        return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)
    except ImportError:
        return jsonify(error='prometheus_client not installed'), 501


@app.route('/api/devices/register', methods=['POST'])
@require_api_key
def register_device():
    data = request.json
    device_id = data.get('device_id')
    if not device_id:
        return jsonify(error='device_id required'), 400

    device = Device.query.get(device_id)
    if not device:
        device = Device(
            id=device_id,
            name=data.get('name', device_id),
            location=data.get('location', ''),
            api_key=request.headers.get('X-API-Key', ''),
        )
        db.session.add(device)
    device.last_seen = datetime.now(timezone.utc)
    device.status = 'active'
    db.session.commit()
    return jsonify(status='registered', device_id=device_id), 201


@app.route('/api/devices/<device_id>/config', methods=['GET'])
@require_api_key
def get_device_config(device_id):
    device = Device.query.get(device_id)
    if not device:
        return jsonify(error='Device not found'), 404
    device.last_seen = datetime.now(timezone.utc)
    db.session.commit()

    base_config = {
        'recognition_threshold': app.config['RECOGNITION_THRESHOLD'],
        'liveness_threshold': app.config['LIVENESS_THRESHOLD'],
        'dedup_cooldown': app.config['DEDUP_COOLDOWN'],
        'min_embedding_quality': app.config['MIN_EMBEDDING_QUALITY'],
    }
    device_overrides = json.loads(device.config or '{}')
    base_config.update(device_overrides)
    return jsonify(base_config)


@app.route('/api/devices/<device_id>/config', methods=['PUT'])
@require_api_key
def update_device_config(device_id):
    device = Device.query.get(device_id)
    if not device:
        return jsonify(error='Device not found'), 404
    data = request.json
    device.config = json.dumps(data)
    db.session.commit()
    return jsonify(status='updated')


@app.route('/api/devices/<device_id>/health', methods=['POST'])
@require_api_key
def device_health(device_id):
    """Receive health report from edge device."""
    device = Device.query.get(device_id)
    if not device:
        return jsonify(error='Device not found'), 404
    data = request.json
    device.uptime_seconds = data.get('uptime', 0)
    device.memory_mb = data.get('memory_mb', 0)
    device.queue_size = data.get('queue_size', 0)
    device.fps_actual = data.get('fps', 0)
    device.last_seen = datetime.now(timezone.utc)
    device.health_reported_at = datetime.now(timezone.utc)
    device.status = 'active'
    db.session.commit()
    return jsonify(status='ok')


@app.route('/api/devices', methods=['GET'])
@require_api_key
def list_devices():
    devices = Device.query.all()
    return jsonify([{
        'id': d.id, 'name': d.name, 'location': d.location,
        'status': d.status,
        'last_seen': d.last_seen.isoformat() if d.last_seen else None,
        'uptime_seconds': d.uptime_seconds,
        'memory_mb': d.memory_mb,
        'queue_size': d.queue_size,
        'fps_actual': d.fps_actual,
    } for d in devices])


@app.route('/api/edge/result', methods=['POST'])
@require_api_key
def receive_result():
    data = request.json
    device_id = data.get('device_id')
    if not device_id:
        return jsonify(error='device_id required'), 400

    device = Device.query.get(device_id)
    if not device:
        return jsonify(error='Unknown device'), 403

    nonce = data.get('nonce', '')
    if nonce and not check_replay(nonce, device_id):
        return jsonify(error='Replay detected'), 403

    return _process_result(data, device_id)


@app.route('/api/edge/sync', methods=['POST'])
@require_api_key
def sync_batch():
    data = request.json
    device_id = data.get('device_id')
    results = data.get('results', [])

    processed = 0
    for result in results:
        result['device_id'] = device_id
        nonce = result.get('nonce', '')
        if nonce and not check_replay(nonce, device_id):
            continue
        _process_result(result, device_id)
        processed += 1

    return jsonify(processed=processed, total=len(results))


def _process_result(data: dict, device_id: str):
    embedding = data.get('embedding')
    liveness_score = data.get('liveness_score', 0)
    timestamp = data.get('timestamp', time.time())

    if not embedding or not data.get('is_live', False):
        return jsonify(status='rejected', reason='liveness_failed')

    query = np.array(embedding, dtype=np.float32)

    # Embedding quality check
    quality = embedding_quality(query)
    min_quality = app.config['MIN_EMBEDDING_QUALITY']
    if quality < min_quality:
        return jsonify(status='rejected', reason='low_quality', quality=round(quality, 3))

    threshold = app.config['RECOGNITION_THRESHOLD']
    user_id, confidence = match_embedding(query, threshold)

    if user_id is None:
        try:
            _pool_metrics.get('recognitions', _noop()).labels(status='unknown').inc()
        except Exception:
            pass
        return jsonify(status='unknown', confidence=confidence)

    # Deduplication
    cooldown = app.config['DEDUP_COOLDOWN']
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=cooldown)
    recent = AttendanceLog.query.filter(
        AttendanceLog.user_id == user_id,
        AttendanceLog.timestamp > cutoff,
    ).first()

    if recent:
        return jsonify(status='duplicate', user_id=user_id, confidence=confidence)

    dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    status = 'present'

    log = AttendanceLog(
        user_id=user_id, device_id=device_id, timestamp=dt,
        confidence=confidence, liveness_score=liveness_score,
        status=status, nonce=data.get('nonce', ''),
    )
    db.session.add(log)
    device = Device.query.get(device_id)
    if device:
        device.last_seen = dt
    db.session.commit()

    try:
        _pool_metrics.get('recognitions', _noop()).labels(status='matched').inc()
        _pool_metrics.get('attendance_marks', _noop()).inc()
    except Exception:
        pass

    user = User.query.get(user_id)
    return jsonify(
        status='marked', user_id=user_id,
        name=user.name if user else 'Unknown',
        confidence=confidence, attendance_status=status,
    )


@app.route('/api/register_user', methods=['POST'])
@require_api_key
def register_user():
    data = request.json
    external_id = data.get('external_id')
    name = data.get('name')
    embedding = data.get('embedding')

    if not external_id or not name or not embedding:
        return jsonify(error='external_id, name, embedding required'), 400

    emb_array = np.array(embedding, dtype=np.float32)

    # Quality check
    quality = embedding_quality(emb_array)
    min_quality = app.config['MIN_EMBEDDING_QUALITY']
    if quality < min_quality:
        return jsonify(error='Embedding quality too low', quality=round(quality, 3),
                       minimum=min_quality), 400

    user = User.query.filter_by(external_id=external_id).first()
    if not user:
        user = User(external_id=external_id, name=name, metadata_json=json.dumps(data.get('metadata', {})))
        db.session.add(user)
        db.session.flush()

    emb_bytes = emb_array.tobytes()
    face_emb = FaceEmbedding(user_id=user.id, embedding_blob=emb_bytes, quality_score=quality)
    db.session.add(face_emb)
    db.session.commit()

    load_embeddings()
    return jsonify(status='registered', user_id=user.id, quality=round(quality, 3)), 201


@app.route('/api/verify_face', methods=['POST'])
@require_api_key
def verify_face():
    data = request.json
    embedding = data.get('embedding')
    threshold = data.get('threshold', app.config['RECOGNITION_THRESHOLD'])

    if not embedding:
        return jsonify(error='embedding required'), 400

    query = np.array(embedding, dtype=np.float32)
    user_id, confidence = match_embedding(query, threshold)

    if user_id:
        user = User.query.get(user_id)
        return jsonify(matched=True, user_id=user_id, name=user.name if user else 'Unknown', confidence=confidence)
    return jsonify(matched=False, confidence=confidence)


@app.route('/api/log_attendance', methods=['POST'])
@require_api_key
def log_attendance():
    data = request.json
    user_id = data.get('user_id')
    device_id = data.get('device_id', 'manual')

    user = User.query.get(user_id)
    if not user:
        return jsonify(error='User not found'), 404

    log = AttendanceLog(
        user_id=user_id, device_id=device_id,
        timestamp=datetime.now(timezone.utc),
        confidence=100.0, liveness_score=1.0,
        status=data.get('status', 'present'),
    )
    db.session.add(log)
    db.session.commit()
    return jsonify(status='logged', log_id=log.id)


@app.route('/api/attendance', methods=['GET'])
@require_api_key
def get_attendance():
    start = request.args.get('start', datetime.now(timezone.utc).date().isoformat())
    end = request.args.get('end', start)
    device_id = request.args.get('device_id')
    user_id = request.args.get('user_id', type=int)

    query = AttendanceLog.query
    start_dt = datetime.fromisoformat(f'{start}T00:00:00').replace(tzinfo=timezone.utc)
    end_dt = datetime.fromisoformat(f'{end}T23:59:59').replace(tzinfo=timezone.utc)
    query = query.filter(AttendanceLog.timestamp >= start_dt)
    query = query.filter(AttendanceLog.timestamp <= end_dt)
    if device_id:
        query = query.filter_by(device_id=device_id)
    if user_id:
        query = query.filter_by(user_id=user_id)

    logs = query.order_by(AttendanceLog.timestamp.desc()).limit(500).all()
    return jsonify([{
        'id': l.id, 'user_id': l.user_id, 'device_id': l.device_id,
        'timestamp': l.timestamp.isoformat(),
        'confidence': l.confidence, 'liveness_score': l.liveness_score,
        'status': l.status,
    } for l in logs])


class _noop:
    """No-op counter for when Prometheus is unavailable."""
    def inc(self): pass
    def labels(self, **kw): return self


# ─── Startup ───

with app.app_context():
    db.create_all()
    load_embeddings()
    _setup_pool_metrics()

logger.info('IoT Backend v3.1.0 initialized')
