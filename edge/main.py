"""Edge device entry point — runs on IoT hardware (RPi, Jetson, Android).

Pipeline:
1. Capture frame (camera stream)
2. Detect face (RetinaFace)
3. Align face using landmarks
4. Generate embedding (ArcFace)
5. Run liveness detection (heuristic + ML)
6. Send embedding + metadata to backend (not raw images)

Supports: offline mode, adaptive FPS, device ID tagging, runtime config updates.
"""

import logging
import time
import signal
import sys
from edge.config.device_config import DeviceConfig
from edge.capture.camera import CameraStream
from edge.inference.pipeline import InferencePipeline
from edge.comms.sync_client import SyncClient
from edge.sync.offline_store import OfflineStore

logger = logging.getLogger(__name__)


class EdgeDevice:
    """Main edge device orchestrator."""

    def __init__(self, config_path: str = 'edge_config.json'):
        self.config = DeviceConfig(config_path)
        self.camera = CameraStream(self.config)
        self.pipeline = InferencePipeline(self.config)
        self.sync = SyncClient(self.config)
        self.offline = OfflineStore(self.config)
        self._running = False
        self._frame_count = 0
        self._device_id = self.config.get('device_id', 'edge-001')

    def start(self):
        """Start the edge device pipeline."""
        logger.info('Edge device %s starting...', self._device_id)
        self._running = True

        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)

        # Try to sync config from backend on startup
        self._sync_config()

        # Start camera
        self.camera.start()

        logger.info('Edge device %s ready (FPS=%d, model=%s)',
                     self._device_id,
                     self.config.get('camera_fps', 15),
                     self.config.get('model_type', 'auto'))

        # Main processing loop
        fps = self.config.get('camera_fps', 15)
        frame_skip = self.config.get('frame_skip', 2)
        interval = 1.0 / fps

        while self._running:
            start_time = time.time()

            frame = self.camera.read()
            if frame is None:
                time.sleep(0.01)
                continue

            self._frame_count += 1

            # Frame skipping for performance
            if self._frame_count % frame_skip != 0:
                continue

            # Process frame
            result = self.pipeline.process(frame)

            if result is not None:
                self._handle_result(result)

            # Adaptive sleep to maintain target FPS
            elapsed = time.time() - start_time
            sleep_time = max(0, interval - elapsed)
            if sleep_time > 0:
                time.sleep(sleep_time)

    def _handle_result(self, result: dict):
        """Handle inference result — send to backend or queue offline."""
        result['device_id'] = self._device_id
        result['timestamp'] = time.time()
        result['nonce'] = f'{self._device_id}:{self._frame_count}:{time.time_ns()}'

        # Try to send to backend
        if self.sync.is_connected():
            success = self.sync.send_result(result)
            if success:
                # Flush any offline queue
                self.offline.flush(self.sync)
                return

        # Backend unreachable — queue for later sync
        self.offline.queue(result)
        logger.debug('Result queued offline (queue_size=%d)', self.offline.queue_size())

    def _sync_config(self):
        """Pull latest config from backend."""
        try:
            remote_config = self.sync.fetch_config()
            if remote_config:
                self.config.merge(remote_config)
                self.config.save()
                logger.info('Config synced from backend')
        except Exception as e:
            logger.warning('Config sync failed: %s', e)

    def _shutdown(self, signum, frame):
        """Graceful shutdown."""
        logger.info('Shutting down edge device %s...', self._device_id)
        self._running = False
        self.camera.stop()
        self.offline.save()
        self.sync.disconnect()
        sys.exit(0)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    )
    device = EdgeDevice()
    device.start()


if __name__ == '__main__':
    main()
