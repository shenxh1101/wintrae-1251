import enum
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import relationship

from app.database import Base


class WaitlistStatus(str, enum.Enum):
    PENDING = "pending"
    NOTIFIED = "notified"
    CONFIRMED = "confirmed"
    DECLINED = "declined"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    ENROLLED = "enrolled"
    ATTENDED = "attended"
    NO_SHOW = "no_show"


class MemberLevel(str, enum.Enum):
    NORMAL = "normal"
    SILVER = "silver"
    GOLD = "gold"
    PLATINUM = "platinum"


class AttendanceStatus(str, enum.Enum):
    PENDING = "pending"
    ATTENDED = "attended"
    NO_SHOW = "no_show"


class NotificationType(str, enum.Enum):
    INVITATION = "invitation"
    REMINDER = "reminder"
    CONFIRMATION = "confirmation"
    TIMEOUT_NOTICE = "timeout_notice"
    CANCEL_NOTICE = "cancel_notice"
    ROLLOVER_NOTICE = "rollover_notice"


class NotificationChannel(str, enum.Enum):
    SMS = "sms"
    EMAIL = "email"
    WECHAT = "wechat"
    APP = "app"


class NotificationStatus(str, enum.Enum):
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    READ = "read"


class Store(Base):
    __tablename__ = "stores"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    address = Column(String(255))
    contact_phone = Column(String(20))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    courses = relationship("Course", back_populates="store")


class Course(Base):
    __tablename__ = "courses"

    id = Column(Integer, primary_key=True, index=True)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    category = Column(String(50))
    total_capacity = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    store = relationship("Store", back_populates="courses")
    slots = relationship("CourseSlot", back_populates="course", cascade="all, delete-orphan")


class CourseSlot(Base):
    __tablename__ = "course_slots"

    id = Column(Integer, primary_key=True, index=True)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    capacity = Column(Integer, nullable=False, default=0)
    enrolled_count = Column(Integer, default=0)
    location = Column(String(100))
    teacher = Column(String(50))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    course = relationship("Course", back_populates="slots")
    waitlist_entries = relationship("WaitlistEntry", back_populates="slot")

    __table_args__ = (
        Index("idx_course_slot_time", "course_id", "start_time"),
    )


class Student(Base):
    __tablename__ = "students"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), nullable=False)
    phone = Column(String(20), nullable=False, unique=True, index=True)
    email = Column(String(100))
    wechat_id = Column(String(50))
    preferred_channel = Column(Enum(NotificationChannel), default=NotificationChannel.SMS)
    member_level = Column(Enum(MemberLevel), default=MemberLevel.NORMAL)
    is_returning_student = Column(Boolean, default=False)
    backup_channels = Column(String(200))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    waitlist_entries = relationship("WaitlistEntry", back_populates="student")


class WaitlistEntry(Base):
    __tablename__ = "waitlist_entries"

    id = Column(Integer, primary_key=True, index=True)
    slot_id = Column(Integer, ForeignKey("course_slots.id"), nullable=False)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    status = Column(Enum(WaitlistStatus), default=WaitlistStatus.PENDING, nullable=False, index=True)
    queue_position = Column(Integer, nullable=False)
    priority_score = Column(Integer, default=0)
    is_urgent = Column(Boolean, default=False)
    notified_at = Column(DateTime)
    confirmed_at = Column(DateTime)
    timeout_at = Column(DateTime)
    cancelled_at = Column(DateTime)
    cancel_reason = Column(String(255))
    attended_at = Column(DateTime)
    attendance_status = Column(Enum(AttendanceStatus), default=AttendanceStatus.PENDING)
    no_show_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    slot = relationship("CourseSlot", back_populates="waitlist_entries")
    student = relationship("Student", back_populates="waitlist_entries")
    notifications = relationship("Notification", back_populates="waitlist_entry")

    __table_args__ = (
        Index("idx_slot_student_status", "slot_id", "student_id", "status"),
        Index("idx_slot_status_created", "slot_id", "status", "created_at"),
        Index("idx_slot_priority_created", "slot_id", "priority_score", "created_at"),
    )


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    waitlist_entry_id = Column(Integer, ForeignKey("waitlist_entries.id"), nullable=False)
    type = Column(Enum(NotificationType), nullable=False)
    channel = Column(Enum(NotificationChannel), nullable=False)
    status = Column(Enum(NotificationStatus), default=NotificationStatus.SENT, nullable=False, index=True)
    content = Column(Text, nullable=False)
    sent_at = Column(DateTime, default=datetime.utcnow)
    delivered_at = Column(DateTime)
    read_at = Column(DateTime)
    error_message = Column(String(255))
    attempt_count = Column(Integer, default=1)
    next_retry_at = Column(DateTime)
    channel_attempt_order = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)

    waitlist_entry = relationship("WaitlistEntry", back_populates="notifications")
    attempts = relationship("NotificationAttempt", back_populates="notification", cascade="all, delete-orphan")


class NotificationAttempt(Base):
    __tablename__ = "notification_attempts"

    id = Column(Integer, primary_key=True, index=True)
    notification_id = Column(Integer, ForeignKey("notifications.id"), nullable=False)
    channel = Column(Enum(NotificationChannel), nullable=False)
    status = Column(Enum(NotificationStatus), nullable=False)
    attempt_number = Column(Integer, nullable=False)
    sent_at = Column(DateTime, default=datetime.utcnow)
    error_message = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)

    notification = relationship("Notification", back_populates="attempts")

    __table_args__ = (
        Index("idx_notification_attempt", "notification_id", "attempt_number"),
    )


class NotificationTimelineEvent(str, enum.Enum):
    CREATED = "created"
    SEND_ATTEMPT = "send_attempt"
    SEND_SUCCESS = "send_success"
    SEND_FAIL = "send_fail"
    RETRY_SCHEDULED = "retry_scheduled"
    DELIVERED = "delivered"
    READ = "read"
    CONFIRMED = "confirmed"
    DECLINED = "declined"
    TIMEOUT = "timeout"


class NotificationTimeline(Base):
    __tablename__ = "notification_timelines"

    id = Column(Integer, primary_key=True, index=True)
    notification_id = Column(Integer, ForeignKey("notifications.id"), nullable=False, index=True)
    event = Column(Enum(NotificationTimelineEvent), nullable=False)
    channel = Column(Enum(NotificationChannel))
    message = Column(String(500))
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    notification = relationship("Notification")

    __table_args__ = (
        Index("idx_notification_timeline", "notification_id", "created_at"),
    )


class PriorityConfig(Base):
    __tablename__ = "priority_configs"

    id = Column(Integer, primary_key=True, index=True)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False, unique=True, index=True)
    member_level_score_normal = Column(Integer, default=0)
    member_level_score_silver = Column(Integer, default=10)
    member_level_score_gold = Column(Integer, default=20)
    member_level_score_platinum = Column(Integer, default=30)
    returning_student_bonus = Column(Integer, default=15)
    urgent_bonus = Column(Integer, default=50)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    course = relationship("Course")


class WaitlistAuditAction(str, enum.Enum):
    CREATED = "created"
    CANCELLED = "cancelled"
    URGENT_UPDATED = "urgent_updated"
    NOTIFIED = "notified"
    CONFIRMED = "confirmed"
    DECLINED = "declined"
    TIMEOUT = "timeout"
    ATTENDED = "attended"
    NO_SHOW = "no_show"
    PRIORITY_RECALCULATED = "priority_recalculated"
    ROLLOVER = "rollover"


class WaitlistAuditLog(Base):
    __tablename__ = "waitlist_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    waitlist_entry_id = Column(Integer, ForeignKey("waitlist_entries.id"), nullable=False, index=True)
    slot_id = Column(Integer, ForeignKey("course_slots.id"), nullable=False, index=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False, index=True)
    action = Column(Enum(WaitlistAuditAction), nullable=False, index=True)
    previous_status = Column(Enum(WaitlistStatus))
    new_status = Column(Enum(WaitlistStatus))
    previous_priority_score = Column(Integer)
    new_priority_score = Column(Integer)
    operator_id = Column(String(100))
    operator_name = Column(String(100))
    source = Column(String(50))
    details = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    waitlist_entry = relationship("WaitlistEntry")
    slot = relationship("CourseSlot")
    student = relationship("Student")

    __table_args__ = (
        Index("idx_audit_slot_student", "slot_id", "student_id", "created_at"),
        Index("idx_audit_action_time", "action", "created_at"),
    )
