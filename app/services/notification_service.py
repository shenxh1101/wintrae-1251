from datetime import datetime
from typing import List, Optional
from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.models import (
    Notification,
    NotificationType,
    NotificationChannel,
    NotificationStatus,
    WaitlistEntry,
)


class NotificationService:
    def create_notification(
        self,
        db: Session,
        waitlist_entry_id: int,
        notification_type: NotificationType,
        channel: NotificationChannel,
        content: str,
    ) -> Notification:
        notification = Notification(
            waitlist_entry_id=waitlist_entry_id,
            type=notification_type,
            channel=channel,
            status=NotificationStatus.SENT,
            content=content,
            sent_at=datetime.utcnow(),
        )
        db.add(notification)
        db.commit()
        db.refresh(notification)
        return notification

    def get_notification(
        self,
        db: Session,
        notification_id: int,
    ) -> Optional[Notification]:
        return db.query(Notification).filter(Notification.id == notification_id).first()

    def get_notifications_by_waitlist(
        self,
        db: Session,
        waitlist_entry_id: int,
        notification_type: Optional[NotificationType] = None,
        status: Optional[NotificationStatus] = None,
    ) -> List[Notification]:
        query = db.query(Notification).filter(
            Notification.waitlist_entry_id == waitlist_entry_id
        )
        if notification_type:
            query = query.filter(Notification.type == notification_type)
        if status:
            query = query.filter(Notification.status == status)
        return query.order_by(Notification.sent_at.desc()).all()

    def get_notifications_by_student(
        self,
        db: Session,
        student_id: int,
        notification_type: Optional[NotificationType] = None,
        status: Optional[NotificationStatus] = None,
        limit: int = 50,
    ) -> List[Notification]:
        query = db.query(Notification).join(WaitlistEntry).filter(
            WaitlistEntry.student_id == student_id
        )
        if notification_type:
            query = query.filter(Notification.type == notification_type)
        if status:
            query = query.filter(Notification.status == status)
        return query.order_by(Notification.sent_at.desc()).limit(limit).all()

    def update_notification_status(
        self,
        db: Session,
        notification_id: int,
        status: NotificationStatus,
        error_message: Optional[str] = None,
    ) -> Optional[Notification]:
        notification = self.get_notification(db, notification_id)
        if not notification:
            return None

        notification.status = status
        if status == NotificationStatus.DELIVERED and not notification.delivered_at:
            notification.delivered_at = datetime.utcnow()
        if status == NotificationStatus.READ and not notification.read_at:
            notification.read_at = datetime.utcnow()
        if error_message:
            notification.error_message = error_message

        db.commit()
        db.refresh(notification)
        return notification

    def get_pending_notifications(
        self,
        db: Session,
        channel: Optional[NotificationChannel] = None,
        limit: int = 100,
    ) -> List[Notification]:
        query = db.query(Notification).filter(
            Notification.status.in_([
                NotificationStatus.SENT,
                NotificationStatus.FAILED,
            ])
        )
        if channel:
            query = query.filter(Notification.channel == channel)
        return query.order_by(Notification.sent_at.asc()).limit(limit).all()

    def mark_notification_read(
        self,
        db: Session,
        notification_id: int,
    ) -> Optional[Notification]:
        return self.update_notification_status(
            db=db,
            notification_id=notification_id,
            status=NotificationStatus.READ,
        )

    def get_notification_stats(
        self,
        db: Session,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> dict:
        query = db.query(Notification)
        if start_date:
            query = query.filter(Notification.sent_at >= start_date)
        if end_date:
            query = query.filter(Notification.sent_at <= end_date)

        total = query.count()
        sent = query.filter(Notification.status == NotificationStatus.SENT).count()
        delivered = query.filter(Notification.status == NotificationStatus.DELIVERED).count()
        read = query.filter(Notification.status == NotificationStatus.READ).count()
        failed = query.filter(Notification.status == NotificationStatus.FAILED).count()

        return {
            "total": total,
            "sent": sent,
            "delivered": delivered,
            "read": read,
            "failed": failed,
            "delivery_rate": delivered / total if total > 0 else 0,
            "read_rate": read / delivered if delivered > 0 else 0,
        }


notification_service = NotificationService()
