"""Offline store — queues results when backend is unreachable.

Persists to disk, auto-syncs when connection restored.
"""

import json
import logging
import os
import time
from collections import deque

logger = logging.getLogger(__name__)


class OfflineStore:
    """Disk-backed queue for offline result storage."""

    def __init__(self, config):
        self._path = config.get('offline_store_path', 'offline_queue.jsonl')
        self._max_size = config.get('offline_queue_max', 1000)
        self._queue: deque = deque()
        self._load()

    def queue(self, result: dict):
        """Add a result to the offline queue."""
        if len(self._queue) >= self._max_size:
            self._queue.popleft()  # Drop oldest
        self._queue.append(result)
        self.save()

    def queue_size(self) -> int:
        return len(self._queue)

    def flush(self, sync_client) -> int:
        """Send all queued results to backend. Returns count sent."""
        if not self._queue:
            return 0

        batch_size = 50
        sent = 0

        while self._queue:
            batch = [self._queue.popleft() for _ in range(min(batch_size, len(self._queue)))]
            if sync_client.send_batch(batch):
                sent += len(batch)
            else:
                # Put unsent items back at front
                for item in reversed(batch):
                    self._queue.appendleft(item)
                break

        if sent > 0:
            logger.info('Flushed %d offline results to backend', sent)
            self.save()

        return sent

    def save(self):
        """Persist queue to disk."""
        try:
            with open(self._path, 'w') as f:
                for item in self._queue:
                    f.write(json.dumps(item) + '\n')
        except Exception as e:
            logger.warning('Failed to save offline queue: %s', e)

    def _load(self):
        """Load queue from disk."""
        if not os.path.exists(self._path):
            return
        try:
            with open(self._path) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        self._queue.append(json.loads(line))
            logger.info('Loaded %d items from offline queue', len(self._queue))
        except Exception as e:
            logger.warning('Failed to load offline queue: %s', e)
