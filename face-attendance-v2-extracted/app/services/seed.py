"""Seed default data on first run."""

import logging
from app.extensions import db
from app.models.user import User
from app.models.schedule import Schedule

logger = logging.getLogger(__name__)


def seed_defaults():
    """Create default admin user and schedules if they don't exist."""

    # Default admin
    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin', role='admin')
        admin.set_password('admin123')  # Change in production!
        db.session.add(admin)
        logger.info('Created default admin user (admin/admin123)')

    # Default teacher
    if not User.query.filter_by(username='teacher').first():
        teacher = User(username='teacher', role='teacher')
        teacher.set_password('teacher123')
        db.session.add(teacher)
        logger.info('Created default teacher user (teacher/teacher123)')

    # Default schedules
    if not Schedule.query.first():
        # Mon-Thu morning
        s1 = Schedule(
            name='Morning Class (Mon-Thu)',
            department=None,
            days_of_week='0,1,2,3',
            start_time='09:45',
            end_time='10:45',
            late_threshold=10,
            grace_period=5,
        )

        # Fri-Sat morning
        s2 = Schedule(
            name='Morning Class (Fri-Sat)',
            department=None,
            days_of_week='4,5',
            start_time='08:45',
            end_time='09:45',
            late_threshold=10,
            grace_period=5,
        )

        db.session.add_all([s1, s2])
        logger.info('Created default schedules (Mon-Thu 9:45, Fri-Sat 8:45)')

    db.session.commit()
