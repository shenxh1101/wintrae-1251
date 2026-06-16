from datetime import datetime, timedelta
from typing import List, Optional, Tuple
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    WaitlistEntry,
    WaitlistStatus,
    CourseSlot,
    Student,
    Course,
    Store,
    Notification,
    NotificationType,
    NotificationChannel,
    NotificationStatus,
)
from app.schemas import (
    WaitlistEntryCreate,
    WaitlistPositionResponse,
    CoursePopularityResponse,
    StoreConversionResponse,
)
from app.services.notification_service import notification_service


class WaitlistService:
    def create_waitlist_entry(
        self,
        db: Session,
        entry_in: WaitlistEntryCreate,
    ) -> WaitlistEntry:
        student = db.query(Student).filter(Student.id == entry_in.student_id).first()
        if not student:
            raise ValueError("Student not found")

        slot = db.query(CourseSlot).filter(CourseSlot.id == entry_in.slot_id).first()
        if not slot or not slot.is_active:
            raise ValueError("Course slot not found or inactive")

        existing = db.query(WaitlistEntry).filter(
            and_(
                WaitlistEntry.slot_id == entry_in.slot_id,
                WaitlistEntry.student_id == entry_in.student_id,
                WaitlistEntry.status.in_([
                    WaitlistStatus.PENDING,
                    WaitlistStatus.NOTIFIED,
                ]),
            )
        ).first()
        if existing:
            raise ValueError("Student is already on the waitlist for this slot")

        active_count = db.query(WaitlistEntry).filter(
            and_(
                WaitlistEntry.student_id == entry_in.student_id,
                WaitlistEntry.status.in_([
                    WaitlistStatus.PENDING,
                    WaitlistStatus.NOTIFIED,
                ]),
            )
        ).count()
        if active_count >= settings.MAX_WAITLIST_PER_STUDENT:
            raise ValueError(
                f"Student has exceeded maximum waitlist limit of {settings.MAX_WAITLIST_PER_STUDENT}"
            )

        current_max_position = db.query(func.max(WaitlistEntry.queue_position)).filter(
            and_(
                WaitlistEntry.slot_id == entry_in.slot_id,
                WaitlistEntry.status.in_([
                    WaitlistStatus.PENDING,
                    WaitlistStatus.NOTIFIED,
                ]),
            )
        ).scalar() or 0

        entry = WaitlistEntry(
            slot_id=entry_in.slot_id,
            student_id=entry_in.student_id,
            status=WaitlistStatus.PENDING,
            queue_position=current_max_position + 1,
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)
        return entry

    def cancel_waitlist_entry(
        self,
        db: Session,
        entry_id: int,
        student_id: int,
        cancel_reason: Optional[str] = None,
    ) -> WaitlistEntry:
        entry = db.query(WaitlistEntry).filter(
            and_(
                WaitlistEntry.id == entry_id,
                WaitlistEntry.student_id == student_id,
            )
        ).first()
        if not entry:
            raise ValueError("Waitlist entry not found")

        if entry.status not in [WaitlistStatus.PENDING, WaitlistStatus.NOTIFIED]:
            raise ValueError("Cannot cancel entry in current status")

        entry.status = WaitlistStatus.CANCELLED
        entry.cancelled_at = datetime.utcnow()
        entry.cancel_reason = cancel_reason

        self._rebuild_queue_positions(db, entry.slot_id)

        notification_service.create_notification(
            db=db,
            waitlist_entry_id=entry.id,
            notification_type=NotificationType.CANCEL_NOTICE,
            channel=entry.student.preferred_channel,
            content=f"您已成功取消【{entry.slot.course.name}】课程候补。",
        )

        db.commit()
        db.refresh(entry)
        return entry

    def get_waitlist_position(
        self,
        db: Session,
        entry_id: int,
    ) -> WaitlistPositionResponse:
        entry = db.query(WaitlistEntry).filter(WaitlistEntry.id == entry_id).first()
        if not entry:
            raise ValueError("Waitlist entry not found")

        total_waiting = db.query(WaitlistEntry).filter(
            and_(
                WaitlistEntry.slot_id == entry.slot_id,
                WaitlistEntry.status.in_([
                    WaitlistStatus.PENDING,
                    WaitlistStatus.NOTIFIED,
                ]),
            )
        ).count()

        current_position = entry.queue_position if entry.status in [
            WaitlistStatus.PENDING, WaitlistStatus.NOTIFIED
        ] else None

        estimated_opportunity = self._calculate_estimated_opportunity(
            db, entry.slot_id, current_position or 0
        )

        return WaitlistPositionResponse(
            entry_id=entry.id,
            slot_id=entry.slot_id,
            course_name=entry.slot.course.name,
            slot_start_time=entry.slot.start_time,
            current_position=current_position or 0,
            total_waiting=total_waiting,
            status=entry.status,
            estimated_opportunity=estimated_opportunity,
            notified_at=entry.notified_at,
            timeout_at=entry.timeout_at,
            created_at=entry.created_at,
        )

    def get_student_waitlists(
        self,
        db: Session,
        student_id: int,
        status: Optional[WaitlistStatus] = None,
    ) -> List[WaitlistEntry]:
        query = db.query(WaitlistEntry).filter(WaitlistEntry.student_id == student_id)
        if status:
            query = query.filter(WaitlistEntry.status == status)
        return query.order_by(WaitlistEntry.created_at.desc()).all()

    def release_slot(
        self,
        db: Session,
        slot_id: int,
        release_count: int = 1,
    ) -> List[WaitlistEntry]:
        slot = db.query(CourseSlot).filter(CourseSlot.id == slot_id).first()
        if not slot:
            raise ValueError("Course slot not found")

        available_slots = slot.capacity - slot.enrolled_count
        if available_slots < release_count:
            raise ValueError(
                f"Insufficient available slots. Available: {available_slots}, Requested: {release_count}"
            )

        notified_entries = []
        for _ in range(release_count):
            next_entry = self._get_next_pending_entry(db, slot_id)
            if not next_entry:
                break

            notified_entry = self._notify_next_in_queue(db, next_entry)
            notified_entries.append(notified_entry)

        return notified_entries

    def confirm_waitlist(
        self,
        db: Session,
        entry_id: int,
        confirmed: bool,
    ) -> WaitlistEntry:
        entry = db.query(WaitlistEntry).filter(WaitlistEntry.id == entry_id).first()
        if not entry:
            raise ValueError("Waitlist entry not found")

        if entry.status != WaitlistStatus.NOTIFIED:
            raise ValueError("Entry is not in notified state")

        if entry.timeout_at and datetime.utcnow() > entry.timeout_at:
            entry.status = WaitlistStatus.TIMEOUT
            db.commit()
            self._process_timeout(db, entry)
            raise ValueError("Confirmation timeout has expired")

        if confirmed:
            entry.status = WaitlistStatus.CONFIRMED
            entry.confirmed_at = datetime.utcnow()
            entry.slot.enrolled_count += 1

            notification_service.create_notification(
                db=db,
                waitlist_entry_id=entry.id,
                notification_type=NotificationType.CONFIRMATION,
                channel=entry.student.preferred_channel,
                content=f"恭喜！您已成功确认【{entry.slot.course.name}】的补位名额，请按时上课。",
            )
        else:
            entry.status = WaitlistStatus.DECLINED
            notification_service.create_notification(
                db=db,
                waitlist_entry_id=entry.id,
                notification_type=NotificationType.CANCEL_NOTICE,
                channel=entry.student.preferred_channel,
                content=f"您已放弃【{entry.slot.course.name}】的补位机会，候补资格已取消。",
            )

        self._rebuild_queue_positions(db, entry.slot_id)

        if not confirmed:
            self._notify_next_pending(db, entry.slot_id)

        db.commit()
        db.refresh(entry)
        return entry

    def process_timeouts(self, db: Session) -> List[WaitlistEntry]:
        now = datetime.utcnow()
        timeout_entries = db.query(WaitlistEntry).filter(
            and_(
                WaitlistEntry.status == WaitlistStatus.NOTIFIED,
                WaitlistEntry.timeout_at <= now,
            )
        ).all()

        processed = []
        for entry in timeout_entries:
            processed_entry = self._process_timeout(db, entry)
            if processed_entry:
                processed.append(processed_entry)

        return processed

    def get_course_popularity_ranking(
        self,
        db: Session,
        store_id: Optional[int] = None,
        limit: int = 20,
    ) -> List[CoursePopularityResponse]:
        query = db.query(
            Course.id,
            Course.name,
            Store.name.label("store_name"),
            Course.category,
            func.count(WaitlistEntry.id).label("total_waitlist_count"),
            func.sum(CourseSlot.capacity).label("total_slots"),
        ).select_from(Course).join(Store).join(CourseSlot).outerjoin(
            WaitlistEntry,
            and_(
                WaitlistEntry.slot_id == CourseSlot.id,
                WaitlistEntry.status.notin_([WaitlistStatus.CANCELLED]),
            )
        ).group_by(Course.id)

        if store_id:
            query = query.filter(Course.store_id == store_id)

        results = query.order_by(func.count(WaitlistEntry.id).desc()).limit(limit).all()

        rankings = []
        for idx, row in enumerate(results):
            total_waitlist = row.total_waitlist_count or 0
            total_slots = row.total_slots or 0
            conversion_rate = (
                min(1.0, total_slots / total_waitlist) if total_waitlist > 0 else 0.0
            )
            rankings.append(CoursePopularityResponse(
                course_id=row.id,
                course_name=row.name,
                store_name=row.store_name,
                category=row.category,
                total_waitlist_count=total_waitlist,
                total_slots=total_slots,
                conversion_rate=round(conversion_rate, 4),
                rank=idx + 1,
            ))

        return rankings

    def get_store_conversion_stats(
        self,
        db: Session,
        store_id: Optional[int] = None,
    ) -> List[StoreConversionResponse]:
        query = db.query(
            Store.id,
            Store.name,
            func.count(func.distinct(Course.id)).label("total_courses"),
            func.count(func.distinct(WaitlistEntry.id)).label("total_waitlist"),
            func.count(func.distinct(
                func.if_(WaitlistEntry.status == WaitlistStatus.CONFIRMED, WaitlistEntry.id, None)
            )).label("total_confirmed"),
            func.count(func.distinct(
                func.if_(WaitlistEntry.status == WaitlistStatus.ENROLLED, WaitlistEntry.id, None)
            )).label("total_enrolled"),
        ).select_from(Store).outerjoin(Course).outerjoin(CourseSlot).outerjoin(
            WaitlistEntry,
            WaitlistEntry.status.notin_([WaitlistStatus.CANCELLED])
        ).group_by(Store.id)

        if store_id:
            query = query.filter(Store.id == store_id)

        results = query.all()

        stats = []
        for row in results:
            total_waitlist = row.total_waitlist or 0
            total_confirmed = row.total_confirmed or 0
            conversion_rate = (
                total_confirmed / total_waitlist if total_waitlist > 0 else 0.0
            )
            avg_wait_time = self._calculate_average_wait_time(db, row.id)

            stats.append(StoreConversionResponse(
                store_id=row.id,
                store_name=row.name,
                total_courses=row.total_courses or 0,
                total_waitlist=total_waitlist,
                total_confirmed=total_confirmed,
                total_enrolled=row.total_enrolled or 0,
                conversion_rate=round(conversion_rate, 4),
                average_wait_time_hours=avg_wait_time,
            ))

        return stats

    def _get_next_pending_entry(
        self,
        db: Session,
        slot_id: int,
    ) -> Optional[WaitlistEntry]:
        return db.query(WaitlistEntry).filter(
            and_(
                WaitlistEntry.slot_id == slot_id,
                WaitlistEntry.status == WaitlistStatus.PENDING,
            )
        ).order_by(
            WaitlistEntry.queue_position.asc(),
            WaitlistEntry.created_at.asc(),
        ).first()

    def _notify_next_in_queue(
        self,
        db: Session,
        entry: WaitlistEntry,
    ) -> WaitlistEntry:
        entry.status = WaitlistStatus.NOTIFIED
        entry.notified_at = datetime.utcnow()
        entry.timeout_at = datetime.utcnow() + timedelta(
            minutes=settings.NOTIFICATION_TIMEOUT_MINUTES
        )

        timeout_minutes = settings.NOTIFICATION_TIMEOUT_MINUTES
        content = (
            f"【补位通知】您好！您候补的【{entry.slot.course.name}】课程已有名额释放。"
            f"请在 {timeout_minutes} 分钟内确认是否接受。课程时间：{entry.slot.start_time.strftime('%Y-%m-%d %H:%M')}。"
        )

        notification_service.create_notification(
            db=db,
            waitlist_entry_id=entry.id,
            notification_type=NotificationType.INVITATION,
            channel=entry.student.preferred_channel,
            content=content,
        )

        db.commit()
        db.refresh(entry)
        return entry

    def _notify_next_pending(self, db: Session, slot_id: int) -> None:
        next_entry = self._get_next_pending_entry(db, slot_id)
        if next_entry:
            self._notify_next_in_queue(db, next_entry)

    def _process_timeout(
        self,
        db: Session,
        entry: WaitlistEntry,
    ) -> Optional[WaitlistEntry]:
        if entry.status != WaitlistStatus.NOTIFIED:
            return None

        entry.status = WaitlistStatus.TIMEOUT

        notification_service.create_notification(
            db=db,
            waitlist_entry_id=entry.id,
            notification_type=NotificationType.TIMEOUT_NOTICE,
            channel=entry.student.preferred_channel,
            content=f"您候补的【{entry.slot.course.name}】课程确认已超时，候补资格已取消。",
        )

        self._rebuild_queue_positions(db, entry.slot_id)
        self._notify_next_pending(db, entry.slot_id)

        db.commit()
        db.refresh(entry)
        return entry

    def _rebuild_queue_positions(self, db: Session, slot_id: int) -> None:
        active_entries = db.query(WaitlistEntry).filter(
            and_(
                WaitlistEntry.slot_id == slot_id,
                WaitlistEntry.status.in_([
                    WaitlistStatus.PENDING,
                    WaitlistStatus.NOTIFIED,
                ]),
            )
        ).order_by(
            WaitlistEntry.created_at.asc(),
            WaitlistEntry.id.asc(),
        ).all()

        for idx, entry in enumerate(active_entries, start=1):
            entry.queue_position = idx

        db.commit()

    def _calculate_estimated_opportunity(
        self,
        db: Session,
        slot_id: int,
        position: int,
    ) -> float:
        slot = db.query(CourseSlot).filter(CourseSlot.id == slot_id).first()
        if not slot:
            return 0.0

        recent_confirmed = db.query(WaitlistEntry).filter(
            and_(
                WaitlistEntry.slot_id == slot_id,
                WaitlistEntry.status == WaitlistStatus.CONFIRMED,
                WaitlistEntry.created_at >= datetime.utcnow() - timedelta(days=30),
            )
        ).count()

        total_recent = db.query(WaitlistEntry).filter(
            and_(
                WaitlistEntry.slot_id == slot_id,
                WaitlistEntry.created_at >= datetime.utcnow() - timedelta(days=30),
            )
        ).count()

        if total_recent == 0 or position == 0:
            base_rate = 0.3
        else:
            base_rate = min(1.0, recent_confirmed / total_recent)

        slot_turnover = slot.capacity * 0.15

        if position <= slot_turnover:
            opportunity = base_rate * 0.9
        elif position <= slot_turnover * 2:
            opportunity = base_rate * 0.6
        elif position <= slot_turnover * 3:
            opportunity = base_rate * 0.3
        else:
            opportunity = base_rate * 0.1

        return round(opportunity, 4)

    def _calculate_average_wait_time(
        self,
        db: Session,
        store_id: int,
    ) -> Optional[float]:
        confirmed_entries = db.query(WaitlistEntry).join(CourseSlot).join(Course).filter(
            and_(
                Course.store_id == store_id,
                WaitlistEntry.status.in_([
                    WaitlistStatus.CONFIRMED,
                    WaitlistStatus.ENROLLED,
                ]),
                WaitlistEntry.notified_at.isnot(None),
                WaitlistEntry.created_at.isnot(None),
            )
        ).all()

        if not confirmed_entries:
            return None

        total_hours = 0.0
        for entry in confirmed_entries:
            if entry.notified_at and entry.created_at:
                wait_time = (entry.notified_at - entry.created_at).total_seconds() / 3600
                total_hours += wait_time

        return round(total_hours / len(confirmed_entries), 2)


waitlist_service = WaitlistService()
