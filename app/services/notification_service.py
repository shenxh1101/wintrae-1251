from datetime import datetime, timedelta
from typing import List, Optional
import random
from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.models import (
    Notification,
    NotificationAttempt,
    NotificationType,
    NotificationChannel,
    NotificationStatus,
    WaitlistEntry,
    Student,
)
from app.config import settings


class NotificationService:
    def _get_channel_list(self, student: Student) -> List[NotificationChannel]:
        channels = []
        if student.preferred_channel:
            channels.append(student.preferred_channel)
        if student.backup_channels:
            for ch in student.backup_channels.split(","):
                ch = ch.strip().lower()
                try:
                    channel = NotificationChannel(ch)
                    if channel not in channels:
                        channels.append(channel)
                except ValueError:
                    pass
        for ch in [NotificationChannel.SMS, NotificationChannel.WECHAT, NotificationChannel.APP, NotificationChannel.EMAIL]:
            if ch not in channels:
                channels.append(ch)
        return channels

    def _simulate_channel_send(self, channel: NotificationChannel, student: Student) -> tuple[bool, Optional[str]]:
        if channel == NotificationChannel.SMS and not student.phone:
            return False, "No phone number"
        if channel == NotificationChannel.EMAIL and not student.email:
            return False, "No email address"
        if channel == NotificationChannel.WECHAT and not student.wechat_id:
            return False, "No WeChat ID"
        if random.random() < 0.1:
            return False, f"{channel.value} service temporarily unavailable"
        return True, None

    def create_notification(
        self,
        db: Session,
        waitlist_entry_id: int,
        notification_type: NotificationType,
        content: str,
    ) -> Notification:
        waitlist_entry = db.query(WaitlistEntry).filter(
            WaitlistEntry.id == waitlist_entry_id
        ).first()
        if not waitlist_entry:
            raise ValueError(f"Waitlist entry {waitlist_entry_id} not found")

        student = waitlist_entry.student
        channels = self._get_channel_list(student)
        channel_order_str = ",".join([c.value for c in channels])

        notification = Notification(
            waitlist_entry_id=waitlist_entry_id,
            type=notification_type,
            channel=channels[0],
            status=NotificationStatus.SENT,
            content=content,
            sent_at=datetime.utcnow(),
            attempt_count=0,
            channel_attempt_order=channel_order_str,
        )
        db.add(notification)
        db.flush()

        success = False
        error_msg = None
        for idx, channel in enumerate(channels):
            attempt_num = idx + 1
            ok, err = self._simulate_channel_send(channel, student)
            attempt = NotificationAttempt(
                notification_id=notification.id,
                channel=channel,
                status=NotificationStatus.SENT if ok else NotificationStatus.FAILED,
                attempt_number=attempt_num,
                sent_at=datetime.utcnow(),
                error_message=err,
            )
            db.add(attempt)
            notification.attempt_count = attempt_num

            if ok:
                notification.channel = channel
                notification.status = NotificationStatus.SENT
                notification.error_message = None
                success = True
                break
            else:
                error_msg = f"{channel.value}: {err}"
                notification.error_message = error_msg
                notification.status = NotificationStatus.FAILED

        if not success and notification.attempt_count < settings.MAX_NOTIFICATION_RETRIES:
            notification.next_retry_at = datetime.utcnow() + timedelta(minutes=settings.NOTIFICATION_RETRY_INTERVAL_MINUTES)

        db.commit()
        db.refresh(notification)
        return notification

    def retry_notification(
        self,
        db: Session,
        notification_id: int,
    ) -> Optional[Notification]:
        notification = self.get_notification(db, notification_id)
        if not notification:
            return None
        if notification.status != NotificationStatus.FAILED:
            return notification
        if notification.attempt_count >= settings.MAX_NOTIFICATION_RETRIES:
            return notification

        waitlist_entry = notification.waitlist_entry
        student = waitlist_entry.student
        channels = self._get_channel_list(student)
        current_attempt = notification.attempt_count

        if current_attempt >= len(channels):
            next_channel_idx = current_attempt % len(channels)
        else:
            next_channel_idx = current_attempt

        channel = channels[next_channel_idx]
        attempt_num = current_attempt + 1
        ok, err = self._simulate_channel_send(channel, student)

        attempt = NotificationAttempt(
            notification_id=notification.id,
            channel=channel,
            status=NotificationStatus.SENT if ok else NotificationStatus.FAILED,
            attempt_number=attempt_num,
            sent_at=datetime.utcnow(),
            error_message=err,
        )
        db.add(attempt)
        notification.attempt_count = attempt_num

        if ok:
            notification.channel = channel
            notification.status = NotificationStatus.SENT
            notification.error_message = None
            notification.next_retry_at = None
        else:
            notification.error_message = f"{channel.value}: {err}"
            notification.status = NotificationStatus.FAILED
            if attempt_num < settings.MAX_NOTIFICATION_RETRIES:
                notification.next_retry_at = datetime.utcnow() + timedelta(minutes=settings.NOTIFICATION_RETRY_INTERVAL_MINUTES)
            else:
                notification.next_retry_at = None

        db.commit()
        db.refresh(notification)
        return notification

    def retry_pending_notifications(
        self,
        db: Session,
        limit: int = 50,
    ) -> List[Notification]:
        now = datetime.utcnow()
        pending = db.query(Notification).filter(
            and_(
                Notification.status == NotificationStatus.FAILED,
                Notification.next_retry_at.isnot(None),
                Notification.next_retry_at <= now,
                Notification.attempt_count < settings.MAX_NOTIFICATION_RETRIES,
            )
        ).order_by(Notification.next_retry_at.asc()).limit(limit).all()

        retried = []
        for n in pending:
            result = self.retry_notification(db, n.id)
            if result:
                retried.append(result)
        return retried

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

        total_attempts = db.query(NotificationAttempt).count()
        avg_attempts = total_attempts / total if total > 0 else 0

        return {
            "total": total,
            "sent": sent,
            "delivered": delivered,
            "read": read,
            "failed": failed,
            "total_attempts": total_attempts,
            "avg_attempts_per_notification": round(avg_attempts, 2),
            "delivery_rate": delivered / total if total > 0 else 0,
            "read_rate": read / delivered if delivered > 0 else 0,
        }


notification_service = NotificationService()
