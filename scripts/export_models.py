#!/usr/bin/env python3
"""Export InsightFace models to ONNX format for Android deployment.

Downloads and converts:
- RetinaFace (buffalo_s lightweight) for face detection
- ArcFace (buffalo_s) for face embedding

Usage:
    python scripts/export_models.py

Output:
    edge/android/app/src/main/assets/
        retinaface_mnet25.onnx   (~5MB)
        arcface_r100.onnx        (~25MB for buffalo_l, ~4MB for buffalo_s)
"""

import os
import sys
import shutil

ASSETS_DIR = os.path.join(os.path.dirname(__file__), '..', 'edge', 'android', 'app', 'src', 'main', 'assets')


def export_models():
    os.makedirs(ASSETS_DIR, exist_ok=True)

    try:
        import insightface
        from insightface.app import FaceAnalysis
    except ImportError:
        print("ERROR: insightface not installed. Run: pip install insightface onnxruntime")
        sys.exit(1)

    print("Downloading buffalo_s models (lightweight for mobile)...")
    app = FaceAnalysis(name='buffalo_s', allowed_modules=['detection', 'recognition'])
    app.prepare(ctx_id=0, det_size=(640, 640))

    # Find model files in InsightFace cache
    cache_dir = os.path.expanduser('~/.insightface/models/buffalo_s')

    if not os.path.exists(cache_dir):
        print(f"ERROR: Model cache not found at {cache_dir}")
        print("Models should have been downloaded during FaceAnalysis init")
        sys.exit(1)

    # Copy detection model
    det_model = os.path.join(cache_dir, 'det_10g.onnx')
    if os.path.exists(det_model):
        shutil.copy(det_model, os.path.join(ASSETS_DIR, 'retinaface_mnet25.onnx'))
        size_mb = os.path.getsize(det_model) / 1024 / 1024
        print(f"  Detection model: {size_mb:.1f}MB -> retinaface_mnet25.onnx")
    else:
        print(f"  WARNING: Detection model not found at {det_model}")

    # Copy recognition model
    rec_model = os.path.join(cache_dir, 'w600k_r50.onnx')
    if os.path.exists(rec_model):
        shutil.copy(rec_model, os.path.join(ASSETS_DIR, 'arcface_r100.onnx'))
        size_mb = os.path.getsize(rec_model) / 1024 / 1024
        print(f"  Embedding model: {size_mb:.1f}MB -> arcface_r100.onnx")
    else:
        print(f"  WARNING: Recognition model not found at {rec_model}")

    print(f"\nModels exported to: {ASSETS_DIR}")
    print("\nTo build the Android app:")
    print("  cd edge/android")
    print("  ./gradlew assembleDebug")
    print("  adb install app/build/outputs/apk/debug/app-debug.apk")


if __name__ == '__main__':
    export_models()
