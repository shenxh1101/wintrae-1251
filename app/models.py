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
    notified_at = Column(DateTime)
    confirmed_at = Column(DateTime)
    timeout_at = Column(DateTime)
    cancelled_at = Column(DateTime)
    cancel_reason = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    slot = relationship("CourseSlot", back_populates="waitlist_entries")
    student = relationship("Student", back_populates="waitlist_entries")
    notifications = relationship("Notification", back_populates="waitlist_entry")

    __table_args__ = (
        UniqueConstraint("slot_id", "student_id", name="uix_slot_student"),
        Index("idx_slot_status_created", "slot_id", "status", "created_at"),
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
    created_at = Column(DateTime, default=datetime.utcnow)

    waitlist_entry = relationship("WaitlistEntry", back_populates="notifications")
