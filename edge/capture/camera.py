"""Camera stream abstraction — supports USB, Pi camera, IP cameras."""

import logging
import threading
import numpy as np

logger = logging.getLogger(__name__)


class CameraStream:
    """Threaded camera capture with configurable source and resolution."""

    def __init__(self, config):
        self._device = config.get('camera_device', 0)
        self._width = config.get('camera_width', 640)
        self._height = config.get('camera_height', 480)
        self._fps = config.get('camera_fps', 15)
        self._cap = None
        self._frame = None
        self._lock = threading.Lock()
        self._running = False
        self._thread = None

    def start(self):
        """Start camera capture thread."""
        import cv2

        # Handle different camera sources
        source = self._device
        if isinstance(source, str) and source.startswith('http'):
            self._cap = cv2.VideoCapture(source)  # IP camera / RTSP
        elif isinstance(source, str) and source.startswith('csi://'):
            # Raspberry Pi CSI camera via GStreamer
            pipeline = f'nvarguscamerasrc ! video/x-raw(memory:NVMM), width={self._width}, height={self._height}, framerate={self._fps}/1 ! nvvidconv ! video/x-raw, format=BGRx ! videoconvert ! appsink'
            self._cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
        else:
            try:
                self._cap = cv2.VideoCapture(int(source))
            except (ValueError, TypeError):
                self._cap = cv2.VideoCapture(str(source))

        if not self._cap.isOpened():
            raise RuntimeError(f'Cannot open camera: {source}')

        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._height)
        self._cap.set(cv2.CAP_PROP_FPS, self._fps)

        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        logger.info('Camera started: %s (%dx%d @ %dfps)', source, self._width, self._height, self._fps)

    def _capture_loop(self):
        """Continuous frame capture loop."""
        while self._running:
            ret, frame = self._cap.read()
            if ret:
                with self._lock:
                    self._frame = frame

    def read(self) -> np.ndarray | None:
        """Get the latest frame (non-blocking)."""
        with self._lock:
            return self._frame.copy() if self._frame is not None else None

    def stop(self):
        """Stop camera and release resources."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        if self._cap:
            self._cap.release()
        logger.info('Camera stopped')
