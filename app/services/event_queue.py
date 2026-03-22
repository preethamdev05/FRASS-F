"""Async attendance logging via Redis Streams.

Decouples face recognition from database writes.
Producer: attendance.py mark_attendance() pushes to stream.
Consumer: background greenlet processes stream and writes to DB.
"""

import json
import logging
import threading
import time

logger = logging.getLogger(__name__)

STREAM_KEY = 'fras:attendance_events'
CONSUMER_GROUP = 'attendance_writers'
CONSUMER_NAME = 'writer_1'


class AttendanceEventQueue:
    """Redis Streams-based async attendance event queue."""

    def __init__(self, redis_client=None):
        self._redis = redis_client
        self._consumer_started = False

    def enqueue(self, event: dict) -> bool:
        """Push an attendance event to the stream.

        Args:
            event: Dict with keys: student_db_id, session_id, confidence,
                   method, liveness_score, timestamp

        Returns:
            True if enqueued, False if Redis unavailable (falls back to sync)
        """
        if not self._redis:
            return False

        try:
            self._redis.xadd(STREAM_KEY, {'data': json.dumps(event)}, maxlen=5000)
            return True
        except Exception as e:
            logger.warning('Stream enqueue failed: %s', e)
            return False

    def start_consumer(self, write_fn):
        """Start a background consumer that processes the stream.

        Args:
            write_fn: Callable that takes an event dict and writes to DB.
                      Called in a background greenlet.
        """
        if self._consumer_started or not self._redis:
            return

        try:
            self._redis.xgroup_create(STREAM_KEY, CONSUMER_GROUP, id='0', mkstream=True)
        except Exception:
            pass  # Group already exists

        def _consume():
            while True:
                try:
                    results = self._redis.xreadgroup(
                        CONSUMER_GROUP, CONSUMER_NAME,
                        {STREAM_KEY: '>'},
                        count=10, block=5000,
                    )
                    for stream, messages in results:
                        for msg_id, data in messages:
                            try:
                                event = json.loads(data.get('data', '{}'))
                                write_fn(event)
                                self._redis.xack(STREAM_KEY, CONSUMER_GROUP, msg_id)
                            except Exception as e:
                                logger.error('Event processing failed: %s', e)
                except Exception:
                    time.sleep(1)

        t = threading.Thread(target=_consume, daemon=True, name='attendance-consumer')
        t.start()
        self._consumer_started = True
        logger.info('Attendance event consumer started')

    def pending_count(self) -> int:
        """Get count of pending (unacknowledged) events."""
        if not self._redis:
            return 0
        try:
            info = self._redis.xpending(STREAM_KEY, CONSUMER_GROUP)
            return info.get('pending', 0) if isinstance(info, dict) else 0
        except Exception:
            return 0
