from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, Field, field_validator

from app.models import (
    WaitlistStatus,
    NotificationType,
    NotificationChannel,
    NotificationStatus,
)


class StoreBase(BaseModel):
    name: str = Field(..., max_length=100)
    address: Optional[str] = Field(None, max_length=255)
    contact_phone: Optional[str] = Field(None, max_length=20)


class StoreCreate(StoreBase):
    pass


class StoreUpdate(StoreBase):
    name: Optional[str] = Field(None, max_length=100)
    is_active: Optional[bool] = None


class StoreResponse(StoreBase):
    id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CourseBase(BaseModel):
    store_id: int
    name: str = Field(..., max_length=100)
    description: Optional[str] = None
    category: Optional[str] = Field(None, max_length=50)
    total_capacity: int = Field(..., ge=0)


class CourseCreate(CourseBase):
    pass


class CourseUpdate(CourseBase):
    store_id: Optional[int] = None
    name: Optional[str] = Field(None, max_length=100)
    total_capacity: Optional[int] = Field(None, ge=0)
    is_active: Optional[bool] = None


class CourseResponse(CourseBase):
    id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CourseSlotBase(BaseModel):
    course_id: int
    start_time: datetime
    end_time: datetime
    capacity: int = Field(..., ge=0)
    location: Optional[str] = Field(None, max_length=100)
    teacher: Optional[str] = Field(None, max_length=50)

    @field_validator("end_time")
    def end_time_after_start_time(cls, v, values):
        if "start_time" in values.data and v <= values.data["start_time"]:
            raise ValueError("end_time must be after start_time")
        return v


class CourseSlotCreate(CourseSlotBase):
    pass


class CourseSlotUpdate(BaseModel):
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    capacity: Optional[int] = Field(None, ge=0)
    enrolled_count: Optional[int] = Field(None, ge=0)
    location: Optional[str] = Field(None, max_length=100)
    teacher: Optional[str] = Field(None, max_length=50)
    is_active: Optional[bool] = None


class CourseSlotResponse(CourseSlotBase):
    id: int
    enrolled_count: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    course: Optional[CourseResponse] = None

    class Config:
        from_attributes = True


class StudentBase(BaseModel):
    name: str = Field(..., max_length=50)
    phone: str = Field(..., max_length=20)
    email: Optional[str] = Field(None, max_length=100)
    wechat_id: Optional[str] = Field(None, max_length=50)
    preferred_channel: Optional[NotificationChannel] = NotificationChannel.SMS


class StudentCreate(StudentBase):
    pass


class StudentUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=50)
    phone: Optional[str] = Field(None, max_length=20)
    email: Optional[str] = Field(None, max_length=100)
    wechat_id: Optional[str] = Field(None, max_length=50)
    preferred_channel: Optional[NotificationChannel] = None


class StudentResponse(StudentBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class WaitlistEntryCreate(BaseModel):
    slot_id: int
    student_id: int


class WaitlistEntryCancel(BaseModel):
    cancel_reason: Optional[str] = Field(None, max_length=255)


class WaitlistEntryConfirm(BaseModel):
    confirmed: bool


class WaitlistPositionResponse(BaseModel):
    entry_id: int
    slot_id: int
    course_name: str
    slot_start_time: datetime
    current_position: int
    total_waiting: int
    status: WaitlistStatus
    estimated_opportunity: float
    notified_at: Optional[datetime]
    timeout_at: Optional[datetime]
    created_at: datetime


class WaitlistEntryResponse(BaseModel):
    id: int
    slot_id: int
    student_id: int
    status: WaitlistStatus
    queue_position: int
    notified_at: Optional[datetime]
    confirmed_at: Optional[datetime]
    timeout_at: Optional[datetime]
    cancelled_at: Optional[datetime]
    cancel_reason: Optional[str]
    created_at: datetime
    updated_at: datetime
    student: Optional[StudentResponse] = None
    slot: Optional[CourseSlotResponse] = None

    class Config:
        from_attributes = True


class NotificationResponse(BaseModel):
    id: int
    waitlist_entry_id: int
    type: NotificationType
    channel: NotificationChannel
    status: NotificationStatus
    content: str
    sent_at: datetime
    delivered_at: Optional[datetime]
    read_at: Optional[datetime]
    error_message: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class CoursePopularityResponse(BaseModel):
    course_id: int
    course_name: str
    store_name: str
    category: Optional[str]
    total_waitlist_count: int
    total_slots: int
    conversion_rate: float
    rank: int


class StoreConversionResponse(BaseModel):
    store_id: int
    store_name: str
    total_courses: int
    total_waitlist: int
    total_confirmed: int
    total_enrolled: int
    conversion_rate: float
    average_wait_time_hours: Optional[float]


class SlotReleaseRequest(BaseModel):
    slot_id: int
    release_count: int = Field(..., ge=1)


class PaginatedResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List
