"""Notification service (in-app via WebSocket, email, Telegram)."""

import logging
import os
import json

logger = logging.getLogger(__name__)


class NotificationService:
    """Send notifications through configured channels."""

    def __init__(self, app=None):
        self.app = app
        self._email_enabled = False
        self._telegram_enabled = False
        self._telegram_bot = None

    def init_app(self, app):
        self.app = app
        # Email setup
        smtp_host = os.environ.get('SMTP_HOST')
        if smtp_host:
            self._email_enabled = True
            logger.info(f'Email notifications enabled (SMTP: {smtp_host})')

        # Telegram setup
        telegram_token = os.environ.get('TELEGRAM_BOT_TOKEN')
        if telegram_token:
            self._telegram_enabled = True
            logger.info('Telegram notifications enabled')

    def notify(self, event: str, data: dict, channels: list = None):
        """Send notification to specified channels."""
        if channels is None:
            channels = ['in_app']

        for channel in channels:
            try:
                if channel == 'in_app':
                    self._send_in_app(event, data)
                elif channel == 'email':
                    self._send_email(event, data)
                elif channel == 'telegram':
                    self._send_telegram(event, data)
            except Exception as e:
                logger.error(f'Notification failed ({channel}): {e}')

    def _send_in_app(self, event: str, data: dict):
        """In-app notification via WebSocket (handled by realtime module)."""
        from app.extensions import socketio
        socketio.emit(event, data, room='notifications')

    def _send_email(self, event: str, data: dict):
        """Send email notification (stub — configure SMTP)."""
        if not self._email_enabled:
            return
        # TODO: implement SMTP email
        logger.info(f'Email notification: {event}')

    def _send_telegram(self, event: str, data: dict):
        """Send Telegram notification."""
        if not self._telegram_enabled:
            return
        # TODO: implement Telegram bot
        logger.info(f'Telegram notification: {event}')


# Singleton
_notification_service = NotificationService()


def get_notification_service() -> NotificationService:
    return _notification_service
