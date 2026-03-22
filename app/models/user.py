"""User model (authentication + RBAC + MFA)."""

from datetime import datetime, timezone
from app.extensions import db

try:
    from argon2 import PasswordHasher as _PasswordHasher
    _ph = _PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)
except ImportError:
    _ph = None


class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=True)
    password_hash = db.Column(db.String(512), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='teacher')  # admin, teacher, student
    is_active = db.Column(db.Boolean, default=True)

    # MFA fields
    mfa_enabled = db.Column(db.Boolean, default=False)
    mfa_secret = db.Column(db.String(32), nullable=True)  # TOTP secret (base32)

    # Account lockout
    failed_login_attempts = db.Column(db.Integer, default=0)
    locked_until = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    # Optional link to student profile
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=True)

    def set_password(self, password: str):
        """Hash password using argon2id (falls back to werkzeug if unavailable)."""
        if _ph is not None:
            self.password_hash = _ph.hash(password)
        else:
            from werkzeug.security import generate_password_hash
            self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """Verify password against stored hash."""
        if _ph is not None:
            from argon2.exceptions import VerifyMismatchError, InvalidHashError
            try:
                return _ph.verify(self.password_hash, password)
            except VerifyMismatchError:
                return False
            except InvalidHashError:
                # Hash was created by werkzeug — fall through
                pass

        # Fallback: werkzeug hash
        try:
            from werkzeug.security import check_password_hash
            return check_password_hash(self.password_hash, password)
        except Exception:
            return False

    def is_locked(self) -> bool:
        """Check if account is currently locked out."""
        if not self.locked_until:
            return False
        now = datetime.now(timezone.utc)
        locked = self.locked_until
        if locked.tzinfo is None:
            locked = locked.replace(tzinfo=timezone.utc)
        if locked > now:
            return True
        # Lockout expired — reset
        self.failed_login_attempts = 0
        self.locked_until = None
        return False

    def record_failed_login(self, max_attempts: int = 5, lockout_seconds: int = 300):
        """Increment failed login counter and lock if threshold reached."""
        self.failed_login_attempts = (self.failed_login_attempts or 0) + 1
        if self.failed_login_attempts >= max_attempts:
            from datetime import timedelta
            self.locked_until = datetime.now(timezone.utc) + timedelta(seconds=lockout_seconds)
        db.session.commit()

    def record_successful_login(self):
        """Reset failed login counter on successful login."""
        self.failed_login_attempts = 0
        self.locked_until = None
        db.session.commit()

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'role': self.role,
            'is_active': self.is_active,
            'mfa_enabled': self.mfa_enabled,
            'student_id': self.student_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
