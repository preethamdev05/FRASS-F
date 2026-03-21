# 🎓 Face Recognition Attendance System

**AI-powered automatic attendance for college students.**

Runs locally — no cloud, no API keys, no data leaves your machine.

## Features

- 📸 **Live face recognition** — real-time attendance via webcam
- 👤 **Student registration** — capture face photos with webcam or upload
- 📊 **Dashboard** — attendance stats, department breakdown, trends
- 📋 **Manual override** — mark attendance manually when needed
- 📥 **CSV export** — download attendance reports
- 🔄 **Cross-platform** — Windows, macOS, Linux
- ⚡ **GPU auto-detect** — uses CUDA/DirectML when available, falls back to CPU

## One-Command Start

```bash
bash run.sh
```

That's it. Opens at `http://localhost:5000`.

## Manual Setup

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
./venv/bin/python models.py     # init database
./venv/bin/python app.py        # start server
```

## How It Works

1. **Register students** → Add student info, then capture 3-5 face photos via webcam
2. **Start attendance** → Point camera at a group, system recognizes faces in real-time
3. **Auto-logs** → Attendance recorded with timestamp, confidence score
4. **Review** → Dashboard shows who's present, absent, and late

## Tech Stack

| Component | Tech | Why |
|-----------|------|-----|
| Face Recognition | **InsightFace (ArcFace)** | 99.83% LFW accuracy, state-of-the-art |
| Inference | **ONNX Runtime** | GPU-accelerated, minimal RAM (~300MB) |
| Detection | **SCRFD** | Fast single-stage face detector |
| Backend | **Flask 3.0** | Lightweight, battle-tested |
| Database | **SQLite** | Zero-config, runs anywhere |
| Frontend | **Vanilla JS** | No build step, works everywhere |

### Why not face_recognition/dlib?

- dlib requires C++ compilation (painful on many systems)
- face_recognition = 99.38% accuracy, InsightFace = 99.83%
- ONNX Runtime has native GPU support
- InsightFace is the 2026 gold standard

## Architecture

```
face-attendance-system/
├── app.py                  # Flask backend + API
├── face_engine.py          # InsightFace recognition engine
├── camera.py               # Webcam stream handler
├── models.py               # Database models (SQLite)
├── run.sh                  # One-command launcher
├── requirements.txt        # Python dependencies
├── static/
│   ├── css/style.css       # Modern dark UI
│   └── js/app.js           # Frontend logic
├── templates/
│   ├── base.html           # Layout
│   ├── dashboard.html      # Main dashboard
│   ├── register.html       # Student registration
│   ├── attendance.html     # Live attendance
│   ├── students.html       # Student management
│   └── reports.html        # Attendance history
├── face_data/              # Student face images
└── attendance_logs/        # Exported reports
```

## System Requirements

- Python 3.10+
- Webcam (USB or built-in)
- ~500MB RAM (model + app)
- Works on: Windows 10+, macOS 11+, Ubuntu 20.04+, Raspberry Pi 4+
- Optional: NVIDIA GPU for faster inference

## Deployment Notes

- **Single-worker only** — Attendance state is held in-memory. Do not run with Gunicorn `--workers > 1` or multiple uWSGI processes. Use `python app.py` or `flask run` (single process).
- **Localhost by default** — The server binds to `127.0.0.1`. To access from other devices on your network, set `host="0.0.0.0"` in `app.py`, but be aware this exposes the app without authentication.
- **Camera teardown** — The webcam is automatically released on process exit via `atexit`, even if killed abruptly.
