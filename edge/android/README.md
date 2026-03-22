# FRAS Android App

Native Android face recognition attendance app.

## Requirements

- Android 8.0+ (API 26)
- Camera with autofocus
- Backend server running (see main README)

## Build

```bash
# 1. Export ONNX models from InsightFace
python3 scripts/export_models.py

# 2. Build APK
cd edge/android
./gradlew assembleDebug

# 3. Install
adb install app/build/outputs/apk/debug/app-debug.apk
```

## Architecture

```
MainActivity
├── CameraManager (CameraX → YUV → Bitmap)
├── InferencePipeline
│   ├── FaceEngine (ONNX Runtime → RetinaFace detect + ArcFace embed)
│   └── LivenessChecker (texture + skin + quality)
├── SyncManager
│   ├── ApiService (Retrofit REST client)
│   ├── OfflineResultDao (Room DB → offline queue)
│   └── AttendanceLogDao (Room DB → local cache)
└── ConfigDialog (backend URL, device ID, API key)
```

## Features

- **On-device face detection** via ONNX Runtime with NNAPI acceleration
- **512-D face embedding** (ArcFace) for recognition
- **Heuristic liveness** (texture variance, skin color, brightness)
- **Offline mode** — results queued to Room DB, synced when reconnected
- **Device health reporting** — uptime, memory, queue size sent periodically
- **Configurable** — backend URL, device ID, API key via settings dialog
- **CameraX** — front camera with frame analysis pipeline
- **Material Design 3** UI

## Configuration

Tap the gear icon to configure:
- **Backend URL**: `http://192.168.1.100:8000` (or your server)
- **Device ID**: Unique identifier for this device (e.g., `android-001`)
- **API Key**: Authentication key from backend

## How It Works

1. Tap **Start Attendance**
2. Camera opens and begins face detection
3. When a face is detected:
   - Quality check (blur, brightness, resolution)
   - Face embedding extracted (512 floats)
   - Liveness check (texture, skin color)
   - Embedding sent to backend for matching
4. Backend matches against enrolled users
5. Result displayed: name, confidence, status
6. If offline: result queued locally, synced later

## Models

Place ONNX models in `app/src/main/assets/`:
- `retinaface_mnet25.onnx` — face detection (~5MB)
- `arcface_r100.onnx` — face embedding (~25MB)

Run `python3 scripts/export_models.py` to auto-export from InsightFace.
