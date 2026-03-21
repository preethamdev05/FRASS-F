# Face Recognition Attendance System v2.0 — Master Blueprint

> **Goal:** Transform from a working prototype into a production-grade, hardware-adaptive, anti-spoof attendance platform.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                   Client Layer                       │
│  PWA (React/Vanilla+HTMX)  ·  WebSocket Live Feed   │
│  Charts (Chart.js)  ·  PDF Export (client-side)      │
└──────────────┬──────────────────────┬───────────────┘
               │ HTTP/REST            │ WebSocket (ws://)
┌──────────────▼──────────────────────▼───────────────┐
│               API Gateway (Flask + Flask-SocketIO)   │
│  JWT Auth  ·  Rate Limiting  ·  Role Middleware      │
├─────────────────────────────────────────────────────┤
│                  Service Layer                       │
│  AttendanceService  ·  FaceEngineService             │
│  ScheduleService    ·  NotificationService           │
│  ExportService      ·  AuditService                  │
├─────────────────────────────────────────────────────┤
│                  Core Engine                         │
│  HardwareDetector  ·  AdaptivePipeline               │
│  LivenessDetector  ·  FaceRecognizer                 │
├─────────────────────────────────────────────────────┤
│                  Data Layer                          │
│  PostgreSQL (via SQLAlchemy)  ·  Redis (cache/queue) │
│  File Storage (face images + encodings)              │
└─────────────────────────────────────────────────────┘
```

---

## Phase 1: Foundation (Backend Core)

### 1.1 — Docker & Docker Compose

**Files:**
- `Dockerfile` — Multi-stage build (Python 3.12 slim base)
- `docker-compose.yml` — Flask + PostgreSQL 16 + Redis 7
- `.env.example` — Config template
- `scripts/init-db.sh` — Auto-create tables on first run

**Stack:**
```yaml
services:
  app:
    build: .
    ports: ["5000:5000"]
    depends_on: [db, redis]
    environment:
      - DATABASE_URL=postgresql://user:pass@db:5432/attendance
      - REDIS_URL=redis://redis:6379/0
      - JWT_SECRET_KEY=${JWT_SECRET_KEY}
      - FLASK_ENV=production
    volumes:
      - face_data:/app/face_data
    deploy:
      resources:
        limits:
          memory: 2G

  db:
    image: postgres:16-alpine
    volumes:
      - pgdata:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data
```

**Best practices:**
- Non-root user in container
- Health checks for all services
- `.dockerignore` to keep image small
- Gunicorn with 4 workers for production

---

### 1.2 — PostgreSQL Migration

**Replace SQLite with PostgreSQL via SQLAlchemy ORM.**

**Models (updated schema):**
```python
class User(db.Model):          # Auth users (admin, teacher, student)
    id, username, email, password_hash, role, created_at, is_active

class Student(db.Model):       # Student profiles
    id, student_id, name, email, department, semester,
    photo_count, is_active, created_at, updated_at

class FaceEncoding(db.Model):  # Face embeddings
    id, student_id, encoding_blob, photo_path, created_at

class AttendanceRecord(db.Model):
    id, student_id, session_id, date, time_in, time_out,
    status (present/late/absent/excused), confidence,
    method (face/manual), liveness_score, notes, created_at

class AttendanceSession(db.Model):  # A single attendance-taking session
    id, started_by (user_id), started_at, ended_at,
    schedule_id, tolerance, status (active/ended)

class Schedule(db.Model):      # Configurable class schedules
    id, name, days_of_week (array), start_time, end_time,
    late_threshold_minutes, department, is_active, created_at

class AuditLog(db.Model):
    id, user_id, action, entity_type, entity_id,
    details (JSON), ip_address, created_at
```

**Migration tool:** Alembic (via Flask-Migrate)

---

### 1.3 — JWT Authentication & RBAC

**Library:** Flask-JWT-Extended

**Roles:**
| Role | Permissions |
|------|------------|
| `admin` | Full access: manage users, students, schedules, system config |
| `teacher` | Run attendance sessions, view reports, manage own students |
| `student` | View own attendance, export own records |

**Endpoints:**
```
POST /api/auth/login        → { access_token, refresh_token }
POST /api/auth/refresh      → new access_token
POST /api/auth/register     → admin only, create teacher/student accounts
POST /api/auth/change-password
GET  /api/auth/me           → current user info
```

**Middleware:**
- `@jwt_required()` on all protected routes
- `@role_required('admin', 'teacher')` decorator
- Token blacklist via Redis for logout

---

### 1.4 — Rate Limiting & Security

**Library:** Flask-Limiter (backed by Redis)

```python
# Global: 100 requests/minute per IP
# Auth endpoints: 5 attempts/minute per IP
# Recognition: 30 requests/minute (prevent brute-force scanning)
# Export: 10 requests/minute
```

**Additional:**
- CORS whitelist (configurable origins)
- Helmet-style security headers
- Input validation via marshmallow/pydantic
- SQL injection prevention (ORM handles this)
- XSS: Content-Security-Policy headers

---

## Phase 2: Intelligence Layer

### 2.1 — Hardware Detection & Adaptive Pipeline

**New file:** `hardware.py`

```python
class HardwareProfile:
    """Detect and profile system capabilities."""

    cpu_cores: int
    cpu_freq_ghz: float
    ram_gb: float
    gpu_type: str          # 'nvidia_cuda' | 'amd_rocm' | 'apple_metal' | 'intel_igpu' | 'none'
    gpu_vram_gb: float
    gpu_name: str

    @staticmethod
    def detect() -> 'HardwareProfile':
        """
        Detection order:
        1. NVIDIA GPU → CUDA (check torch.cuda / onnxruntime CUDA EP)
        2. AMD GPU → ROCm (check torch ROCm)
        3. Apple Silicon → CoreML/Metal (platform == darwin, arm64)
        4. Intel iGPU → OpenVINO (check onnxruntime OpenVINO EP)
        5. Fallback → CPU
        """

    def optimal_config(self) -> EngineConfig:
        """Return config tuned for this hardware."""
```

**Adaptive Engine Config:**

| Hardware Tier | Detection | Encoding | Parallel Workers | Batch Size | Resolution |
|--------------|-----------|----------|-----------------|------------|------------|
| **High GPU** (8GB+ VRAM) | CUDA/Metal FP16 | GPU batch | 4 workers | 16 faces | 640px |
| **Mid GPU** (2-4GB VRAM) | CUDA FP32 | GPU single | 2 workers | 4 faces | 480px |
| **Intel iGPU** | OpenVINO | CPU+accel | 2 workers | 2 faces | 480px |
| **Apple Silicon** | CoreML | ANE | 2 workers | 8 faces | 640px |
| **High CPU** (8+ cores) | ONNX CPU | ThreadPool | CPU_count/2 | 4 faces | 480px |
| **Low CPU** (2-4 cores) | ONNX CPU | Single thread | 1 worker | 1 face | 320px |
| **Low RAM** (<4GB) | ONNX CPU lite | Single thread | 1 worker | 1 face | 320px |

**Implementation:**
```python
class AdaptiveEngine:
    def __init__(self, profile: HardwareProfile):
        self.profile = profile
        self.config = profile.optimal_config()
        self.session = self._create_session()

    def _create_session(self):
        """Create ONNX Runtime session with optimal execution providers."""
        import onnxruntime as ort
        providers = []

        if self.profile.gpu_type == 'nvidia_cuda':
            providers.append(('CUDAExecutionProvider', {
                'device_id': 0,
                'arena_extend_strategy': 'kSameAsRequested',
                'gpu_mem_limit': int(self.profile.gpu_vram_gb * 0.7 * 1024 * 1024 * 1024),
            }))
        elif self.profile.gpu_type == 'apple_metal':
            providers.append('CoreMLExecutionProvider')
        elif self.profile.gpu_type == 'intel_igpu':
            providers.append(('OpenVINOExecutionProvider', {
                'device_type': 'GPU_FP16' if self.profile.gpu_vram_gb > 1 else 'CPU_FP32',
            }))

        providers.append(('CPUExecutionProvider', {
            'intra_op_num_threads': max(1, self.profile.cpu_cores - 1),
            'inter_op_num_threads': max(1, self.profile.cpu_cores // 2),
        }))

        return ort.InferenceSession(self.model_path, providers=providers)

    def detect_faces(self, frame):
        """Resize frame based on config before detection."""

    def encode_faces(self, faces, frame):
        """Batch or single encode based on hardware tier."""
```

**Memory management:**
- Monitor RAM usage, degrade quality under pressure
- Unload model from GPU when idle (configurable timeout)
- Lazy-load model on first request, not at startup
- Configurable max concurrent recognitions

---

### 2.2 — Liveness Detection (Anti-Spoofing)

**Goal:** Prevent students from holding up a photo/screen to the camera.

**Multi-layer approach (no single method is foolproof):**

**Layer 1: Texture Analysis**
```python
class LivenessDetector:
    def check_texture(self, face_roi) -> float:
        """
        Use LBP (Local Binary Patterns) variance.
        Real faces have micro-texture; printed photos/screens are smooth.
        Score: 0.0 (fake) → 1.0 (real)
        """
```

**Layer 2: Moiré Pattern Detection**
```python
    def check_moire(self, face_roi) -> float:
        """
        Screens exhibit moiré patterns under camera.
        FFT-based frequency analysis detects periodic screen artifacts.
        """
```

**Layer 3: Depth Estimation (face landmark geometry)**
```python
    def check_depth(self, landmarks) -> float:
        """
        Real faces have 3D depth: nose bridge forward, eyes inset.
        Flat photos produce flat landmark geometry.
        Compare nose-to-eye distance ratios.
        """
```

**Layer 4: Blink/Motion Detection**
```python
    def check_motion(self, face_history: list) -> float:
        """
        Track face across 5-10 frames.
        Real faces exhibit micro-movements (blinks, subtle head motion).
        Static photos = identical frames.
        EAR (Eye Aspect Ratio) for blink detection.
        """
```

**Layer 5: Color Space Analysis**
```python
    def check_colorspace(self, face_roi) -> float:
        """
        Real skin has specific YCrCb color distribution.
        Screen photos shift color space differently.
        Check if skin-tone pixels fall within natural range.
        """
```

**Combined score:**
```python
def compute_liveness(self, face_roi, landmarks, face_history) -> LivenessResult:
    scores = {
        'texture': self.check_texture(face_roi) * 0.25,
        'moire': self.check_moire(face_roi) * 0.20,
        'depth': self.check_depth(landmarks) * 0.25,
        'motion': self.check_motion(face_history) * 0.20,
        'colorspace': self.check_colorspace(face_roi) * 0.10,
    }
    total = sum(scores.values())
    return LivenessResult(
        score=total,
        is_live=total >= self.threshold,  # configurable, default 0.6
        breakdown=scores
    )
```

**Configurable:** Admin can set liveness threshold, enable/disable individual checks.

---

### 2.3 — Attendance Schedules & Timetables

**Database model:**
```python
class Schedule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))           # "CS101 Morning"
    department = db.Column(db.String(50))
    days_of_week = db.Column(db.ARRAY(db.Integer))  # [0,1,2,3] = Mon-Thu
    start_time = db.Column(db.Time)            # 09:45:00
    end_time = db.Column(db.Time)              # 10:45:00
    late_threshold = db.Column(db.Integer)     # 10 minutes
    grace_period = db.Column(db.Integer)       # 5 min buffer before marking absent
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime)
```

**Default schedules (pre-seeded):**
```
Mon-Thu Morning:  09:45 - 10:45  late_threshold=10min
Fri-Sat Morning:  08:45 - 09:45  late_threshold=10min
```

**Admin can:**
- Create/edit/delete schedules via UI
- Set per-department schedules
- Override for specific dates (holidays, special events)
- Set "no attendance" days

**Logic:**
```python
def determine_status(schedule, marked_time):
    now = datetime.now()
    start = datetime.combine(now.date(), schedule.start_time)

    if marked_time <= start + timedelta(minutes=schedule.late_threshold):
        return 'present'
    elif marked_time <= start + timedelta(minutes=schedule.late_threshold + schedule.grace_period):
        return 'late'
    else:
        return 'late'  # still accepted, just late
```

---

### 2.4 — WebSocket Real-Time Updates

**Library:** Flask-SocketIO + python-socketio

```python
@socketio.on('connect')
def handle_connect():
    join_room('attendance_dashboard')

@socketio.on('join_session')
def handle_join_session(data):
    join_room(f'session_{data["session_id"]}')
```

**Events pushed to clients:**
```python
# When face recognized
socketio.emit('face_recognized', {
    'student_id': 'CS2024001',
    'name': 'Preetham N',
    'confidence': 94.5,
    'liveness_score': 0.87,
    'timestamp': '2026-03-21T09:47:00',
    'photo': 'base64_thumbnail...'
}, room=f'session_{session_id}')

# When student marked
socketio.emit('student_marked', {
    'student_id': 'CS2024001',
    'name': 'Preetham N',
    'status': 'present',
    'time_in': '2026-03-21T09:46:30',
    'total_marked': 42,
    'total_students': 50,
}, room=f'session_{session_id}')

# Dashboard live stats
socketio.emit('stats_update', {
    'present': 42,
    'late': 3,
    'absent': 5,
    'rate': 90.0,
}, room='attendance_dashboard')

# Liveness alert
socketio.emit('spoof_detected', {
    'face_index': 2,
    'reason': 'Low liveness score (0.23). Possible photo/screen.',
    'action': 'skipped',
}, room=f'session_{session_id}')
```

**Frontend integration:**
```javascript
const socket = io();

socket.on('student_marked', (data) => {
    // Update table, animate new row, play sound
    // No more polling!
});

socket.on('spoof_detected', (data) => {
    showToast(`⚠️ Spoof attempt blocked: ${data.reason}`, 'warning');
});

socket.on('stats_update', (data) => {
    animateCounter(document.getElementById('present'), data.present);
    updateRing(data.rate);
});
```

---

## Phase 3: Frontend Polish

### 3.1 — Chart.js Integration

**Replace the custom bar chart with Chart.js.**

**Dashboard charts:**
- Attendance rate donut (replacing SVG ring — or keep SVG ring, add charts elsewhere)
- Week trend line chart with hover tooltips
- Department comparison bar chart
- Hourly attendance distribution (when do most people arrive?)

**Reports page:**
- Date range line chart (attendance rate over time)
- Per-student attendance heatmap (calendar grid)
- Method breakdown pie (face vs manual)

**Library:** `chart.js@4` (tree-shakeable, ~60KB)

---

### 3.2 — PDF Report Export

**Backend:** WeasyPrint (HTML→PDF) or ReportLab

```python
@app.route('/api/export/pdf', methods=['GET'])
@login_required
@role_required('admin', 'teacher')
def export_pdf():
    """Generate PDF with college branding, charts, tables."""
    records = get_filtered_attendance(...)
    html = render_template('reports/pdf_template.html',
        records=records,
        summary=compute_summary(records),
        generated_at=datetime.now()
    )
    pdf = HTML(string=html).write_pdf()
    return send_file(io.BytesIO(pdf), mimetype='application/pdf')
```

**PDF template includes:**
- College/institution header (configurable logo + name)
- Date range and filters applied
- Summary stats
- Attendance table
- Signature lines
- Page numbers

---

### 3.3 — PWA (Installable App)

**Files to add:**
- `static/manifest.json` — App name, icons, theme, display mode
- `static/sw.js` — Service worker for offline caching
- Icon set: 192x192, 512x512, maskable

**Manifest:**
```json
{
    "name": "FaceAttend",
    "short_name": "FaceAttend",
    "start_url": "/dashboard",
    "display": "standalone",
    "background_color": "#0a0a1a",
    "theme_color": "#00d2ff",
    "icons": [...]
}
```

**Service worker strategy:**
- Cache-first for static assets (CSS, JS, icons)
- Network-first for API calls
- Offline fallback page showing "You're offline, here's cached data"

---

### 3.4 — Bulk Import

**Backend:**
```python
@app.route('/api/students/import', methods=['POST'])
@login_required
@role_required('admin')
def import_students():
    """Accept CSV file, validate, bulk insert."""
    file = request.files['csv']
    results = bulk_import_students(file)  # returns {created: N, skipped: N, errors: [...]}
    return jsonify(results)
```

**CSV format:**
```
student_id,name,email,department,semester
CS2024001,Preetham N,preetham@cs.edu,Computer Science,5
CS2024002,Jane Doe,jane@cs.edu,Computer Science,5
```

**Frontend:** Upload modal with drag-drop, preview table, validation errors shown inline.

---

## Phase 4: Notifications & Audit

### 4.1 — Notification Service

**Channels:**
1. **In-app** (WebSocket toast) — always active
2. **Email** (optional, via SMTP) — daily digest, alerts
3. **Telegram bot** (optional) — instant alerts

**Triggers:**
```
- Student marked present → In-app
- Spoof attempt detected → In-app + Email (admin)
- Student absent 3+ consecutive days → Email teacher + Telegram
- Low attendance rate (<75%) daily summary → Email admin
- System error / model failure → Email admin
```

**Config in DB:**
```python
class NotificationConfig(db.Model):
    user_id, channel (in_app/email/telegram),
    triggers (JSON array), is_enabled
```

---

### 4.2 — Audit Log

**Every mutating action logged:**
```python
def audit_log(user_id, action, entity_type, entity_id, details=None):
    AuditLog.create(
        user_id=user_id,
        action=action,           # 'create', 'update', 'delete', 'mark_attendance', 'login'
        entity_type=entity_type, # 'student', 'attendance', 'schedule', 'user'
        entity_id=entity_id,
        details=details,         # JSON diff of changes
        ip_address=request.remote_addr
    )
```

**Admin audit viewer:**
- Filter by user, action type, date range
- Shows what changed (before → after)
- Export to CSV

---

## File Structure (Final)

```
face-attendance-system/
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── .dockerignore
├── requirements.txt
├── gunicorn.conf.py
├── run.sh                          # Dev mode (updated)
├── run.bat
│
├── app/
│   ├── __init__.py                 # App factory (create_app)
│   ├── config.py                   # Config classes (Dev/Prod/Test)
│   ├── extensions.py               # db, jwt, socketio, limiter, migrate
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── user.py                 # User (auth)
│   │   ├── student.py              # Student
│   │   ├── face.py                 # FaceEncoding
│   │   ├── attendance.py           # AttendanceRecord, AttendanceSession
│   │   ├── schedule.py             # Schedule
│   │   └── audit.py                # AuditLog
│   │
│   ├── auth/
│   │   ├── __init__.py
│   │   ├── routes.py               # login, register, refresh, me
│   │   └── decorators.py           # role_required
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── students.py             # CRUD + import/export
│   │   ├── attendance.py           # sessions, recognize, mark, stats
│   │   ├── schedules.py            # CRUD schedules
│   │   ├── reports.py              # range queries, PDF export
│   │   └── admin.py                # audit log, users, system config
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── face_engine.py          # Face detection + encoding
│   │   ├── liveness.py             # LivenessDetector
│   │   ├── hardware.py             # HardwareProfile + AdaptiveEngine
│   │   ├── attendance.py           # AttendanceService
│   │   ├── notification.py         # NotificationService
│   │   └── export.py               # CSV + PDF generation
│   │
│   ├── realtime/
│   │   ├── __init__.py
│   │   └── events.py               # SocketIO event handlers
│   │
│   ├── templates/
│   │   ├── base.html
│   │   ├── auth/
│   │   │   └── login.html
│   │   ├── dashboard.html
│   │   ├── register.html
│   │   ├── attendance.html
│   │   ├── students.html
│   │   ├── reports.html
│   │   ├── schedules.html          # NEW
│   │   ├── admin/                  # NEW
│   │   │   ├── users.html
│   │   │   ├── audit.html
│   │   │   └── settings.html
│   │   └── reports/
│   │       └── pdf_template.html   # NEW
│   │
│   └── static/
│       ├── css/
│       │   └── style.css
│       ├── js/
│       │   ├── app.js
│       │   ├── charts.js           # NEW (Chart.js wrappers)
│       │   ├── realtime.js         # NEW (SocketIO client)
│       │   └── pwa.js              # NEW (service worker registration)
│       ├── manifest.json           # NEW
│       ├── sw.js                   # NEW
│       └── icons/                  # NEW (PWA icons)
│
├── migrations/                     # Alembic (auto-generated)
├── scripts/
│   ├── init-db.sh
│   ├── seed-schedules.py           # Default schedules
│   └── benchmark.py                # Hardware benchmark tool
│
├── tests/                          # NEW
│   ├── conftest.py
│   ├── test_auth.py
│   ├── test_students.py
│   ├── test_attendance.py
│   ├── test_liveness.py
│   └── test_hardware.py
│
├── face_data/                      # Face images (gitignored, volume-mounted)
└── attendance.db                   # Legacy (removed after PG migration)
```

---

## Implementation Order

| Step | What | Depends On | Est. Complexity |
|------|------|-----------|----------------|
| 1 | Docker + Compose setup | — | Medium |
| 2 | Restructure to app factory pattern | Step 1 | Medium |
| 3 | PostgreSQL + SQLAlchemy models + Alembic | Step 2 | Medium |
| 4 | JWT Auth + RBAC | Step 3 | Medium |
| 5 | Hardware detection + Adaptive engine | Step 2 | High |
| 6 | Liveness detection | Step 5 | High |
| 7 | WebSocket (Flask-SocketIO) | Steps 2, 4 | Medium |
| 8 | Schedule system + configurable timings | Step 3 | Medium |
| 9 | Rate limiting + security headers | Step 4 | Low |
| 10 | Chart.js frontend | Step 7 | Medium |
| 11 | PDF export | Step 3 | Medium |
| 12 | PWA (manifest + service worker) | — | Low |
| 13 | Bulk CSV import | Step 3 | Low |
| 14 | Notification service | Steps 7, 4 | Medium |
| 15 | Audit logging | Step 4 | Low |
| 16 | Login page + admin panel UI | Step 4 | Medium |
| 17 | Tests | All | Medium |
| 18 | Final integration + polish | All | — |

**Strategy:** Steps 1-4 first (foundation), then 5-6 (intelligence), then 7-9 (features), then 10-16 (polish).

---

## Tech Stack Summary

| Layer | Technology |
|-------|-----------|
| **Runtime** | Python 3.12 |
| **Web Framework** | Flask 3.x |
| **Realtime** | Flask-SocketIO + python-socketio |
| **ORM** | SQLAlchemy 2.x + Flask-Migrate (Alembic) |
| **Database** | PostgreSQL 16 |
| **Cache/Queue** | Redis 7 |
| **Auth** | Flask-JWT-Extended |
| **Rate Limiting** | Flask-Limiter |
| **Face Detection** | InsightFace (buffalo_l) |
| **ML Runtime** | ONNX Runtime (auto-select EP) |
| **Anti-Spoof** | Custom liveness (LBP + FFT + EAR + depth) |
| **Frontend** | Jinja2 + Vanilla JS + Chart.js + Socket.IO client |
| **PWA** | Service Worker + Web App Manifest |
| **PDF** | WeasyPrint |
| **Validation** | Marshmallow |
| **Testing** | pytest + pytest-flask |
| **Container** | Docker + Docker Compose |
| **WSGI** | Gunicorn (4 workers) |
| **Reverse Proxy** | Nginx (optional, in compose) |
| **Monitoring** | structlog + optional Sentry |

---

## Hardware Compatibility Matrix

| Hardware | Detection | Inference | Expected Perf |
|----------|-----------|-----------|---------------|
| NVIDIA RTX 3060+ (8GB+) | CUDA FP16 | GPU batch | 15-30 faces/sec |
| NVIDIA GTX 1650 (4GB) | CUDA FP32 | GPU single | 8-15 faces/sec |
| Apple M1/M2/M3 | CoreML → ANE | GPU+ANE | 10-20 faces/sec |
| Intel iGPU (Iris Xe) | OpenVINO GPU | Accelerated | 5-10 faces/sec |
| AMD Ryzen (no dGPU) | CPU AVX2 | ThreadPool | 3-6 faces/sec |
| Intel i5/i7 (no GPU) | CPU AVX2 | ThreadPool | 3-6 faces/sec |
| Raspberry Pi 4 (4GB) | CPU ARM NEON | Single thread | 1-2 faces/sec |
| Low-end (2 cores, 2GB) | CPU basic | Single thread | 0.5-1 faces/sec |

**Graceful degradation:** If GPU OOM, auto-fallback to CPU. If RAM pressure, reduce batch size + resolution.

---

*Blueprint by Kai ⚡ — 2026-03-21*
