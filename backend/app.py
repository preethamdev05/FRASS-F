"""IoT Backend — processing layer for distributed edge devices.

Responsibilities:
- Store embeddings (PostgreSQL + pgvector)
- Perform similarity search (HNSW index)
- Attendance logging with timestamps
- Device management and config distribution
- Replay attack prevention (nonce + timestamp validation)
"""

import os
import logging
import time
import json
import hashlib
import numpy as np
from datetime import datetime, timezone, timedelta
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get('SECRET_KEY', 'iot-backend-secret'),
    SQLALCHEMY_DATABASE_URI=os.environ.get('DATABASE_URL', 'sqlite:///iot_attendance.db'),
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    SQLALCHEMY_ENGINE_OPTIONS={'pool_pre_ping': True, 'pool_size': 20, 'max_overflow': 30},
    REDIS_URL=os.environ.get('REDIS_URL', 'redis://localhost:6379/1'),
    RECOGNITION_THRESHOLD=float(os.environ.get('RECOGNITION_THRESHOLD', '0.65')),
    LIVENESS_THRESHOLD=float(os.environ.get('LIVENESS_THRESHOLD', '0.65')),
    DEDUP_COOLDOWN=int(os.environ.get('DEDUP_COOLDOWN', '300')),  # seconds
    API_KEYS=json.loads(os.environ.get('API_KEYS', '{}')),  # {device_id: api_key}
)

db = SQLAlchemy(app)
CORS(app)

# ─── Models ───

class Device(db.Model):
    __tablename__ = 'devices'
    id = db.Column(db.String(64), primary_key=True)  # device_id
    name = db.Column(db.String(128))
    location = db.Column(db.String(256))
    status = db.Column(db.String(20), default='active')  # active, inactive, maintenance
    last_seen = db.Column(db.DateTime)
    config = db.Column(db.Text, default='{}')  # JSON device-specific config
    registered_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    external_id = db.Column(db.String(64), unique=True, nullable=False)  # from upstream system
    name = db.Column(db.String(128), nullable=False)
    metadata_json = db.Column(db.Text, default='{}')  # department, role, etc.
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class FaceEmbedding(db.Model):
    __tablename__ = 'face_embeddings'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    embedding_blob = db.Column(db.LargeBinary, nullable=False)  # 512 x float32
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
    status = db.Column(db.String(20), default='present')  # present, late, half_day
    session_id = db.Column(db.String(64), index=True)
    nonce = db.Column(db.String(128), unique=True)  # replay prevention


class ReplayGuard(db.Model):
    __tablename__ = 'replay_guard'
    nonce = db.Column(db.String(128), primary_key=True)
    device_id = db.Column(db.String(64), index=True)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


# ─── Embedding Cache ───

_embedding_cache = {}  # {user_id: [np.ndarray, ...]}
_cache_loaded = False


def load_embeddings():
    """Load all embeddings into memory for fast matching."""
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


def match_embedding(query: np.ndarray, threshold: float) -> tuple:
    """Match query embedding against cache. Returns (user_id, confidence) or (None, confidence)."""
    if not _cache_loaded:
        load_embeddings()

    if not _embedding_cache:
        return None, 0.0

    # Try pgvector first
    result = _match_pgvector(query, threshold)
    if result[0] is not None or result[1] > 0:
        return result

    # Fallback: linear scan
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
    """pgvector ANN search."""
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


# ─── Replay Prevention ───

def check_replay(nonce: str, device_id: str) -> bool:
    """Check if nonce has been seen before (replay attack prevention)."""
    if not nonce:
        return False
    existing = ReplayGuard.query.get(nonce)
    if existing:
        return False  # Replay detected
    db.session.add(ReplayGuard(nonce=nonce, device_id=device_id))
    db.session.commit()
    return True


# ─── API Endpoints ───

@app.route('/api/health')
def health():
    try:
        db.session.execute(db.text('SELECT 1'))
        return jsonify(status='healthy', version='3.0.0-iot')
    except Exception:
        return jsonify(status='degraded'), 503


@app.route('/api/devices/register', methods=['POST'])
def register_device():
    """Register a new edge device."""
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
        )
        db.session.add(device)
    device.last_seen = datetime.now(timezone.utc)
    device.status = 'active'
    db.session.commit()
    return jsonify(status='registered', device_id=device_id), 201


@app.route('/api/devices/<device_id>/config', methods=['GET'])
def get_device_config(device_id):
    """Get merged config for a device."""
    device = Device.query.get(device_id)
    if not device:
        return jsonify(error='Device not found'), 404
    device.last_seen = datetime.now(timezone.utc)
    db.session.commit()

    base_config = {
        'recognition_threshold': app.config['RECOGNITION_THRESHOLD'],
        'liveness_threshold': app.config['LIVENESS_THRESHOLD'],
        'dedup_cooldown': app.config['DEDUP_COOLDOWN'],
    }
    device_overrides = json.loads(device.config or '{}')
    base_config.update(device_overrides)
    return jsonify(base_config)


@app.route('/api/devices/<device_id>/config', methods=['PUT'])
def update_device_config(device_id):
    """Update device-specific config overrides."""
    device = Device.query.get(device_id)
    if not device:
        return jsonify(error='Device not found'), 404
    data = request.json
    device.config = json.dumps(data)
    db.session.commit()
    return jsonify(status='updated')


@app.route('/api/devices', methods=['GET'])
def list_devices():
    """List all registered devices."""
    devices = Device.query.all()
    return jsonify([{
        'id': d.id, 'name': d.name, 'location': d.location,
        'status': d.status,
        'last_seen': d.last_seen.isoformat() if d.last_seen else None,
    } for d in devices])


@app.route('/api/edge/result', methods=['POST'])
def receive_result():
    """Receive a single inference result from an edge device."""
    data = request.json
    device_id = data.get('device_id')
    if not device_id:
        return jsonify(error='device_id required'), 400

    # Validate device
    device = Device.query.get(device_id)
    if not device:
        return jsonify(error='Unknown device'), 403

    # Replay prevention
    nonce = data.get('nonce', '')
    if nonce and not check_replay(nonce, device_id):
        return jsonify(error='Replay detected'), 403

    # Process the result
    return _process_result(data, device_id)


@app.route('/api/edge/sync', methods=['POST'])
def sync_batch():
    """Receive a batch of results from offline sync."""
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
    """Process a single face recognition result."""
    embedding = data.get('embedding')
    liveness_score = data.get('liveness_score', 0)
    timestamp = data.get('timestamp', time.time())

    if not embedding or not data.get('is_live', False):
        return jsonify(status='rejected', reason='liveness_failed')

    # Convert to numpy
    query = np.array(embedding, dtype=np.float32)

    # Match against known embeddings
    threshold = app.config['RECOGNITION_THRESHOLD']
    user_id, confidence = match_embedding(query, threshold)

    if user_id is None:
        return jsonify(status='unknown', confidence=confidence)

    # Deduplication: check if this user was already logged recently
    cooldown = app.config['DEDUP_COOLDOWN']
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=cooldown)
    recent = AttendanceLog.query.filter(
        AttendanceLog.user_id == user_id,
        AttendanceLog.timestamp > cutoff,
    ).first()

    if recent:
        return jsonify(status='duplicate', user_id=user_id, confidence=confidence)

    # Determine attendance status
    dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    status = 'present'  # Default; can be enhanced with schedule logic

    # Log attendance
    log = AttendanceLog(
        user_id=user_id,
        device_id=device_id,
        timestamp=dt,
        confidence=confidence,
        liveness_score=liveness_score,
        status=status,
        nonce=data.get('nonce', ''),
    )
    db.session.add(log)
    device = Device.query.get(device_id)
    if device:
        device.last_seen = dt
    db.session.commit()

    user = User.query.get(user_id)
    return jsonify(
        status='marked',
        user_id=user_id,
        name=user.name if user else 'Unknown',
        confidence=confidence,
        attendance_status=status,
    )


@app.route('/api/register_user', methods=['POST'])
def register_user():
    """Register a user with face embedding."""
    data = request.json
    external_id = data.get('external_id')
    name = data.get('name')
    embedding = data.get('embedding')

    if not external_id or not name or not embedding:
        return jsonify(error='external_id, name, embedding required'), 400

    user = User.query.filter_by(external_id=external_id).first()
    if not user:
        user = User(external_id=external_id, name=name, metadata_json=json.dumps(data.get('metadata', {})))
        db.session.add(user)
        db.session.flush()

    emb_bytes = np.array(embedding, dtype=np.float32).tobytes()
    face_emb = FaceEmbedding(user_id=user.id, embedding_blob=emb_bytes, quality_score=data.get('quality', 0))
    db.session.add(face_emb)
    db.session.commit()

    # Reload cache
    load_embeddings()

    return jsonify(status='registered', user_id=user.id), 201


@app.route('/api/verify_face', methods=['POST'])
def verify_face():
    """Verify a face embedding against the database."""
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
def log_attendance():
    """Manual attendance logging."""
    data = request.json
    user_id = data.get('user_id')
    device_id = data.get('device_id', 'manual')

    user = User.query.get(user_id)
    if not user:
        return jsonify(error='User not found'), 404

    log = AttendanceLog(
        user_id=user_id,
        device_id=device_id,
        timestamp=datetime.now(timezone.utc),
        confidence=100.0,
        liveness_score=1.0,
        status=data.get('status', 'present'),
    )
    db.session.add(log)
    db.session.commit()
    return jsonify(status='logged', log_id=log.id)


@app.route('/api/attendance', methods=['GET'])
def get_attendance():
    """Query attendance logs."""
    start = request.args.get('start', datetime.now(timezone.utc).date().isoformat())
    end = request.args.get('end', start)
    device_id = request.args.get('device_id')
    user_id = request.args.get('user_id', type=int)

    query = AttendanceLog.query
    query = query.filter(AttendanceLog.timestamp >= f'{start}T00:00:00')
    query = query.filter(AttendanceLog.timestamp <= f'{end}T23:59:59')
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


# ─── Startup ───

with app.app_context():
    db.create_all()
    load_embeddings()

logger.info('IoT Backend initialized')
