from datetime import datetime, timedelta
from typing import List, Optional, Tuple
from sqlalchemy import and_, func, or_, case
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    WaitlistEntry,
    WaitlistStatus,
    CourseSlot,
    Student,
    Course,
    Store,
    NotificationType,
    MemberLevel,
    AttendanceStatus,
    PriorityConfig,
)
from app.schemas import (
    WaitlistEntryCreate,
    WaitlistPositionResponse,
    CoursePopularityResponse,
    StoreConversionResponse,
    SlotWaitlistDashboardResponse,
)
from app.services.notification_service import notification_service


class WaitlistService:
    def _get_course_priority_config(
        self, db: Session, course_id: int
    ) -> PriorityConfig:
        config = db.query(PriorityConfig).filter(
            and_(
                PriorityConfig.course_id == course_id,
                PriorityConfig.is_active == True,
            )
        ).first()
        return config

    def _get_member_level_score(
        self, config: Optional[PriorityConfig], level: MemberLevel
    ) -> int:
        if config:
            if level == MemberLevel.SILVER:
                return config.member_level_score_silver
            elif level == MemberLevel.GOLD:
                return config.member_level_score_gold
            elif level == MemberLevel.PLATINUM:
                return config.member_level_score_platinum
            return config.member_level_score_normal
        else:
            if level == MemberLevel.SILVER:
                return settings.MEMBER_LEVEL_SCORE_SILVER
            elif level == MemberLevel.GOLD:
                return settings.MEMBER_LEVEL_SCORE_GOLD
            elif level == MemberLevel.PLATINUM:
                return settings.MEMBER_LEVEL_SCORE_PLATINUM
            return settings.MEMBER_LEVEL_SCORE_NORMAL

    def _get_returning_student_bonus(self, config: Optional[PriorityConfig]) -> int:
        return config.returning_student_bonus if config else settings.RETURNING_STUDENT_BONUS

    def _get_urgent_bonus(self, config: Optional[PriorityConfig]) -> int:
        return config.urgent_bonus if config else settings.URGENT_BONUS

    def _calculate_priority_score(
        self,
        student: Student,
        course_id: Optional[int] = None,
        is_urgent: bool = False,
        db: Optional[Session] = None,
    ) -> int:
        config = None
        if course_id and db:
            config = self._get_course_priority_config(db, course_id)

        score = self._get_member_level_score(config, student.member_level)
        if student.is_returning_student:
            score += self._get_returning_student_bonus(config)
        if is_urgent:
            score += self._get_urgent_bonus(config)
        return score

    def _get_priority_reasons(
        self,
        student: Student,
        is_urgent: bool,
        course_id: Optional[int] = None,
        db: Optional[Session] = None,
    ) -> List[str]:
        reasons = []
        level_names = {
            MemberLevel.SILVER: "银牌会员",
            MemberLevel.GOLD: "金牌会员",
            MemberLevel.PLATINUM: "铂金会员",
        }
        config = None
        if course_id and db:
            config = self._get_course_priority_config(db, course_id)

        level_score = self._get_member_level_score(config, student.member_level)
        returning_bonus = self._get_returning_student_bonus(config) if student.is_returning_student else 0
        urgent_bonus = self._get_urgent_bonus(config) if is_urgent else 0

        if student.member_level in level_names and level_score > 0:
            reasons.append(f"{level_names[student.member_level]}加成(+{level_score})")
        if student.is_returning_student and returning_bonus > 0:
            reasons.append(f"老学员加成(+{returning_bonus})")
        if is_urgent and urgent_bonus > 0:
            reasons.append(f"手动加急(+{urgent_bonus})")
        if not reasons:
            reasons.append("按提交时间排序")
        return reasons

    def _cleanup_inactive_entries(
        self,
        db: Session,
        slot_id: int,
        student_id: int,
    ):
        inactive_statuses = [
            WaitlistStatus.CANCELLED,
            WaitlistStatus.DECLINED,
            WaitlistStatus.TIMEOUT,
            WaitlistStatus.ATTENDED,
            WaitlistStatus.NO_SHOW,
            WaitlistStatus.ENROLLED,
        ]
        old_entries = db.query(WaitlistEntry).filter(
            and_(
                WaitlistEntry.slot_id == slot_id,
                WaitlistEntry.student_id == student_id,
                WaitlistEntry.status.in_(inactive_statuses),
            )
        ).all()
        for entry in old_entries:
            db.delete(entry)

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
                    WaitlistStatus.CONFIRMED,
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

        priority_score = self._calculate_priority_score(
            student, slot.course_id, entry_in.is_urgent or False, db
        )

        entry = WaitlistEntry(
            slot_id=entry_in.slot_id,
            student_id=entry_in.student_id,
            status=WaitlistStatus.PENDING,
            queue_position=0,
            priority_score=priority_score,
            is_urgent=entry_in.is_urgent or False,
            attendance_status=AttendanceStatus.PENDING,
        )
        db.add(entry)
        db.flush()
        self._rebuild_queue_positions(db, entry_in.slot_id)
        db.refresh(entry)
        return entry

    def preview_waitlist_position(
        self,
        db: Session,
        slot_id: int,
        student_id: int,
        is_urgent: bool = False,
    ) -> dict:
        student = db.query(Student).filter(Student.id == student_id).first()
        if not student:
            raise ValueError("Student not found")

        slot = db.query(CourseSlot).filter(CourseSlot.id == slot_id).first()
        if not slot or not slot.is_active:
            raise ValueError("Course slot not found or inactive")

        priority_score = self._calculate_priority_score(
            student, slot.course_id, is_urgent, db
        )
        priority_reasons = self._get_priority_reasons(
            student, is_urgent, slot.course_id, db
        )

        pending_entries = db.query(WaitlistEntry).filter(
            and_(
                WaitlistEntry.slot_id == slot_id,
                WaitlistEntry.status.in_([
                    WaitlistStatus.PENDING,
                    WaitlistStatus.NOTIFIED,
                ]),
            )
        ).order_by(
            WaitlistEntry.priority_score.desc(),
            WaitlistEntry.created_at.asc(),
        ).all()

        predicted_position = 1
        for e in pending_entries:
            if (e.priority_score > priority_score) or \
               (e.priority_score == priority_score and e.created_at <= datetime.utcnow()):
                predicted_position += 1
            else:
                break

        total_waiting = len(pending_entries) + 1

        return {
            "slot_id": slot_id,
            "course_name": slot.course.name,
            "slot_start_time": slot.start_time,
            "predicted_position": predicted_position,
            "total_after_submit": total_waiting,
            "priority_score": priority_score,
            "is_urgent": is_urgent,
            "priority_reasons": priority_reasons,
            "member_level": student.member_level.value,
            "is_returning_student": student.is_returning_student,
        }

    def _calculate_available_release_slots(self, db: Session, slot: CourseSlot) -> int:
        notified_count = db.query(WaitlistEntry).filter(
            and_(
                WaitlistEntry.slot_id == slot.id,
                WaitlistEntry.status == WaitlistStatus.NOTIFIED,
            )
        ).count()

        available = slot.capacity - slot.enrolled_count - notified_count
        return max(0, available)

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

        was_notified = entry.status == WaitlistStatus.NOTIFIED

        entry.status = WaitlistStatus.CANCELLED
        entry.cancelled_at = datetime.utcnow()
        entry.cancel_reason = cancel_reason

        self._rebuild_queue_positions(db, entry.slot_id)

        notification_service.create_notification(
            db=db,
            waitlist_entry_id=entry.id,
            notification_type=NotificationType.CANCEL_NOTICE,
            content=f"您已成功取消【{entry.slot.course.name}】课程候补。",
        )

        if was_notified:
            self._notify_next_pending(db, entry.slot_id, rollover_reason="前一位学员主动取消候补")

        db.commit()
        db.refresh(entry)
        return entry

    def mark_attendance(
        self,
        db: Session,
        entry_id: int,
        attendance_status: AttendanceStatus,
    ) -> WaitlistEntry:
        entry = db.query(WaitlistEntry).filter(WaitlistEntry.id == entry_id).first()
        if not entry:
            raise ValueError("Waitlist entry not found")

        if entry.status not in [WaitlistStatus.CONFIRMED, WaitlistStatus.ATTENDED, WaitlistStatus.NO_SHOW]:
            raise ValueError("Can only mark attendance for confirmed or already attended entries")

        previous_status = entry.status

        if attendance_status == AttendanceStatus.ATTENDED:
            entry.status = WaitlistStatus.ATTENDED
            entry.attendance_status = AttendanceStatus.ATTENDED
            entry.attended_at = datetime.utcnow()
            if previous_status == WaitlistStatus.NO_SHOW and entry.slot.enrolled_count < entry.slot.capacity:
                entry.slot.enrolled_count += 1
            notification_service.create_notification(
                db=db,
                waitlist_entry_id=entry.id,
                notification_type=NotificationType.CONFIRMATION,
                content=f"【到课确认】您已成功签到【{entry.slot.course.name}】课程，祝您学习愉快！",
            )
        elif attendance_status == AttendanceStatus.NO_SHOW:
            entry.status = WaitlistStatus.NO_SHOW
            entry.attendance_status = AttendanceStatus.NO_SHOW
            entry.no_show_at = datetime.utcnow()
            if previous_status in [WaitlistStatus.CONFIRMED, WaitlistStatus.ATTENDED] and entry.slot.enrolled_count > 0:
                entry.slot.enrolled_count -= 1
            notification_service.create_notification(
                db=db,
                waitlist_entry_id=entry.id,
                notification_type=NotificationType.CANCEL_NOTICE,
                content=f"【未到课提醒】您未按时参加【{entry.slot.course.name}】课程，本次补位名额已作废。",
            )

        db.commit()
        db.refresh(entry)
        return entry

    def batch_mark_attendance(
        self,
        db: Session,
        slot_id: int,
        attended_ids: List[int] = None,
        no_show_ids: List[int] = None,
    ) -> dict:
        slot = db.query(CourseSlot).filter(CourseSlot.id == slot_id).first()
        if not slot:
            raise ValueError("Course slot not found")

        attended_ids = attended_ids or []
        no_show_ids = no_show_ids or []

        if len(set(attended_ids) & set(no_show_ids)) > 0:
            raise ValueError("An entry cannot be in both attended and no_show lists")

        confirmed_entries = db.query(WaitlistEntry).filter(
            and_(
                WaitlistEntry.slot_id == slot_id,
                WaitlistEntry.status.in_([
                    WaitlistStatus.CONFIRMED,
                    WaitlistStatus.ATTENDED,
                    WaitlistStatus.NO_SHOW,
                ]),
            )
        ).all()
        valid_ids = {e.id for e in confirmed_entries}

        if not set(attended_ids).issubset(valid_ids):
            invalid = set(attended_ids) - valid_ids
            raise ValueError(f"Invalid attended entry IDs: {invalid}")
        if not set(no_show_ids).issubset(valid_ids):
            invalid = set(no_show_ids) - valid_ids
            raise ValueError(f"Invalid no_show entry IDs: {invalid}")

        success_count = 0
        failed_count = 0
        results = []

        for entry_id in attended_ids:
            try:
                self.mark_attendance(db, entry_id, AttendanceStatus.ATTENDED)
                success_count += 1
                results.append({"entry_id": entry_id, "status": "attended", "success": True})
            except Exception as e:
                failed_count += 1
                results.append({"entry_id": entry_id, "status": "attended", "success": False, "error": str(e)})

        for entry_id in no_show_ids:
            try:
                self.mark_attendance(db, entry_id, AttendanceStatus.NO_SHOW)
                success_count += 1
                results.append({"entry_id": entry_id, "status": "no_show", "success": True})
            except Exception as e:
                failed_count += 1
                results.append({"entry_id": entry_id, "status": "no_show", "success": False, "error": str(e)})

        db.commit()

        total_confirmed = len(valid_ids)
        total_attended = db.query(WaitlistEntry).filter(
            and_(
                WaitlistEntry.slot_id == slot_id,
                WaitlistEntry.status == WaitlistStatus.ATTENDED,
            )
        ).count()
        total_no_show = db.query(WaitlistEntry).filter(
            and_(
                WaitlistEntry.slot_id == slot_id,
                WaitlistEntry.status == WaitlistStatus.NO_SHOW,
            )
        ).count()
        total_marked = total_attended + total_no_show
        attendance_rate = round(total_attended / total_marked, 4) if total_marked > 0 else 0.0

        return {
            "slot_id": slot_id,
            "total_confirmed": total_confirmed,
            "total_marked": total_marked,
            "total_attended": total_attended,
            "total_no_show": total_no_show,
            "attendance_rate": attendance_rate,
            "success_count": success_count,
            "failed_count": failed_count,
            "results": results,
        }

    def get_attendance_roster(
        self,
        db: Session,
        store_id: Optional[int] = None,
        course_id: Optional[int] = None,
        slot_id: Optional[int] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> dict:
        slot_query = db.query(CourseSlot).join(Course).join(Store).filter(
            CourseSlot.is_active == True,
            Course.is_active == True,
            Store.is_active == True,
        )

        if slot_id:
            slot_query = slot_query.filter(CourseSlot.id == slot_id)
        if course_id:
            slot_query = slot_query.filter(Course.id == course_id)
        if store_id:
            slot_query = slot_query.filter(Store.id == store_id)
        if date_from:
            slot_query = slot_query.filter(CourseSlot.start_time >= date_from)
        if date_to:
            slot_query = slot_query.filter(CourseSlot.start_time <= date_to)

        slots = slot_query.order_by(CourseSlot.start_time.asc()).all()

        roster_slots = []
        for slot in slots:
            entries = db.query(WaitlistEntry).filter(
                and_(
                    WaitlistEntry.slot_id == slot.id,
                    WaitlistEntry.status.in_([
                        WaitlistStatus.CONFIRMED,
                        WaitlistStatus.ATTENDED,
                        WaitlistStatus.NO_SHOW,
                    ]),
                )
            ).order_by(
                WaitlistEntry.status.asc(),
                WaitlistEntry.created_at.asc(),
            ).all()

            entry_list = []
            total_confirmed = 0
            total_attended = 0
            total_no_show = 0
            total_pending_mark = 0

            for e in entries:
                status = e.status
                if status == WaitlistStatus.CONFIRMED:
                    total_confirmed += 1
                    total_pending_mark += 1
                elif status == WaitlistStatus.ATTENDED:
                    total_attended += 1
                elif status == WaitlistStatus.NO_SHOW:
                    total_no_show += 1

                entry_list.append({
                    "entry_id": e.id,
                    "student_id": e.student_id,
                    "student_name": e.student.name,
                    "student_phone": e.student.phone,
                    "member_level": e.student.member_level.value if e.student.member_level else None,
                    "is_returning_student": e.student.is_returning_student,
                    "status": status.value,
                    "attendance_status": e.attendance_status.value if e.attendance_status else None,
                    "confirmed_at": e.confirmed_at,
                    "attended_at": e.attended_at,
                    "no_show_at": e.no_show_at,
                    "queue_position": e.queue_position,
                    "priority_score": e.priority_score,
                })

            total_marked = total_attended + total_no_show
            attendance_rate = round(total_attended / total_marked, 4) if total_marked > 0 else 0.0
            pending_mark_rate = round(total_pending_mark / len(entries), 4) if len(entries) > 0 else 0.0

            roster_slots.append({
                "slot_id": slot.id,
                "course_id": slot.course_id,
                "store_id": slot.course.store_id,
                "course_name": slot.course.name,
                "store_name": slot.course.store.name,
                "start_time": slot.start_time,
                "end_time": slot.end_time,
                "capacity": slot.capacity,
                "enrolled_count": slot.enrolled_count,
                "teacher": slot.teacher,
                "location": slot.location,
                "total_entries": len(entry_list),
                "total_confirmed_pending_mark": total_pending_mark,
                "total_attended": total_attended,
                "total_no_show": total_no_show,
                "attendance_rate": attendance_rate,
                "pending_mark_rate": pending_mark_rate,
                "entries": entry_list,
            })

        return {
            "total_slots": len(roster_slots),
            "total_entries": sum(s["total_entries"] for s in roster_slots),
            "total_attended": sum(s["total_attended"] for s in roster_slots),
            "total_no_show": sum(s["total_no_show"] for s in roster_slots),
            "slots": roster_slots,
        }

    def set_urgent(
        self,
        db: Session,
        entry_id: int,
        is_urgent: bool,
    ) -> WaitlistEntry:
        entry = db.query(WaitlistEntry).filter(WaitlistEntry.id == entry_id).first()
        if not entry:
            raise ValueError("Waitlist entry not found")

        if entry.status not in [WaitlistStatus.PENDING, WaitlistStatus.NOTIFIED]:
            raise ValueError("Can only set urgent flag for active entries")

        entry.is_urgent = is_urgent
        entry.priority_score = self._calculate_priority_score(
            entry.student, entry.slot.course_id, is_urgent, db
        )

        self._rebuild_queue_positions(db, entry.slot_id)
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
        ] else 0

        estimated_opportunity = self._calculate_estimated_opportunity(
            db, entry.slot_id, current_position
        )

        priority_reasons = self._get_priority_reasons(
            entry.student, entry.is_urgent, entry.slot.course_id, db
        )

        return WaitlistPositionResponse(
            entry_id=entry.id,
            slot_id=entry.slot_id,
            course_name=entry.slot.course.name,
            slot_start_time=entry.slot.start_time,
            current_position=current_position,
            total_waiting=total_waiting,
            status=entry.status,
            estimated_opportunity=estimated_opportunity,
            notified_at=entry.notified_at,
            timeout_at=entry.timeout_at,
            created_at=entry.created_at,
            priority_score=entry.priority_score,
            is_urgent=entry.is_urgent,
            priority_reasons=priority_reasons,
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

        available_slots = self._calculate_available_release_slots(db, slot)

        if available_slots <= 0:
            raise ValueError(
                f"No available slots to release. Capacity: {slot.capacity}, "
                f"Enrolled: {slot.enrolled_count}, Notified pending: "
                f"{slot.capacity - slot.enrolled_count - available_slots}"
            )

        actual_release = min(release_count, available_slots)
        if actual_release < release_count:
            raise ValueError(
                f"Insufficient available slots. Maximum available: {available_slots}, "
                f"Requested: {release_count}. "
                f"(Capacity: {slot.capacity}, Enrolled: {slot.enrolled_count}, "
                f"Pending notification: {slot.capacity - slot.enrolled_count - available_slots})"
            )

        notified_entries = []
        for _ in range(actual_release):
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
            self._process_timeout(db, entry, rollover_reason="学员确认超时")
            raise ValueError("Confirmation timeout has expired")

        if confirmed:
            if entry.slot.enrolled_count >= entry.slot.capacity:
                raise ValueError(
                    f"Cannot confirm: slot is already full. "
                    f"Capacity: {entry.slot.capacity}, Enrolled: {entry.slot.enrolled_count}"
                )

            entry.status = WaitlistStatus.CONFIRMED
            entry.confirmed_at = datetime.utcnow()
            entry.slot.enrolled_count += 1

            notifications = entry.notifications
            if notifications:
                latest = sorted(notifications, key=lambda n: n.sent_at or datetime.min, reverse=True)[0]
                notification_service.add_timeline_event(
                    db, latest.id, "confirmed",
                    message=f"学员确认补位成功",
                )

            notification_service.create_notification(
                db=db,
                waitlist_entry_id=entry.id,
                notification_type=NotificationType.CONFIRMATION,
                content=f"恭喜！您已成功确认【{entry.slot.course.name}】的补位名额，请按时上课。",
            )
        else:
            entry.status = WaitlistStatus.DECLINED

            notifications = entry.notifications
            if notifications:
                latest = sorted(notifications, key=lambda n: n.sent_at or datetime.min, reverse=True)[0]
                notification_service.add_timeline_event(
                    db, latest.id, "declined",
                    message=f"学员主动放弃补位",
                )

            notification_service.create_notification(
                db=db,
                waitlist_entry_id=entry.id,
                notification_type=NotificationType.CANCEL_NOTICE,
                content=f"您已放弃【{entry.slot.course.name}】的补位机会，候补资格已取消。",
            )

        self._rebuild_queue_positions(db, entry.slot_id)

        if not confirmed:
            self._notify_next_pending(db, entry.slot_id, rollover_reason="前一位学员主动放弃补位")

        db.commit()
        db.refresh(entry)
        return entry

    def process_timeouts(
        self,
        db: Session,
        simulate_time: Optional[datetime] = None,
        slot_id: Optional[int] = None,
    ) -> List[WaitlistEntry]:
        now = simulate_time or datetime.utcnow()
        query = db.query(WaitlistEntry).filter(
            and_(
                WaitlistEntry.status == WaitlistStatus.NOTIFIED,
                WaitlistEntry.timeout_at <= now,
            )
        )

        if slot_id:
            query = query.filter(WaitlistEntry.slot_id == slot_id)

        timeout_entries = query.all()

        processed = []
        for entry in timeout_entries:
            processed_entry = self._process_timeout(
                db, entry, rollover_reason="学员确认超时", simulate_time=simulate_time
            )
            if processed_entry:
                processed.append(processed_entry)

        return processed

    def _get_next_pending_entry(
        self, db: Session, slot_id: int
    ) -> Optional[WaitlistEntry]:
        return db.query(WaitlistEntry).filter(
            and_(
                WaitlistEntry.slot_id == slot_id,
                WaitlistEntry.status == WaitlistStatus.PENDING,
            )
        ).order_by(
            WaitlistEntry.priority_score.desc(),
            WaitlistEntry.created_at.asc(),
        ).first()

    def _notify_next_in_queue(
        self, db: Session, entry: WaitlistEntry
    ) -> WaitlistEntry:
        entry.status = WaitlistStatus.NOTIFIED
        entry.notified_at = datetime.utcnow()
        entry.timeout_at = datetime.utcnow() + timedelta(
            minutes=settings.NOTIFICATION_TIMEOUT_MINUTES
        )
        entry.queue_position = 0

        notification_service.create_notification(
            db=db,
            waitlist_entry_id=entry.id,
            notification_type=NotificationType.INVITATION,
            content=(
                f"【补位邀请】您已获得【{entry.slot.course.name}】课程的补位机会，"
                f"请在 {settings.NOTIFICATION_TIMEOUT_MINUTES} 分钟内确认，逾期将自动顺延。"
            ),
        )

        db.commit()
        db.refresh(entry)
        return entry

    def _notify_next_pending(
        self,
        db: Session,
        slot_id: int,
        rollover_reason: str,
    ) -> Optional[WaitlistEntry]:
        available = self._calculate_available_release_slots(
            db, db.query(CourseSlot).filter(CourseSlot.id == slot_id).first()
        )
        if available <= 0:
            return None

        next_entry = self._get_next_pending_entry(db, slot_id)
        if not next_entry:
            return None

        notified = self._notify_next_in_queue(db, next_entry)

        notification_service.create_notification(
            db=db,
            waitlist_entry_id=notified.id,
            notification_type=NotificationType.ROLLOVER_NOTICE,
            content=f"【顺延通知】{rollover_reason}，您获得了补位机会。",
        )

        return notified

    def _process_timeout(
        self,
        db: Session,
        entry: WaitlistEntry,
        rollover_reason: str,
        simulate_time: Optional[datetime] = None,
    ) -> Optional[WaitlistEntry]:
        if entry.status != WaitlistStatus.NOTIFIED:
            return None

        entry.status = WaitlistStatus.TIMEOUT

        notifications = entry.notifications
        if notifications:
            latest = sorted(notifications, key=lambda n: n.sent_at or datetime.min, reverse=True)[0]
            notification_service.add_timeline_event(
                db, latest.id, "timeout",
                message=f"{rollover_reason}，自动顺延下一位",
            )

        notification_service.create_notification(
            db=db,
            waitlist_entry_id=entry.id,
            notification_type=NotificationType.TIMEOUT_NOTICE,
            content=f"【超时提醒】您未在规定时间内确认【{entry.slot.course.name}】的补位名额，资格已顺延。",
        )

        self._rebuild_queue_positions(db, entry.slot_id)
        self._notify_next_pending(db, entry.slot_id, rollover_reason=rollover_reason)

        db.commit()
        db.refresh(entry)
        return entry

    def _rebuild_queue_positions(self, db: Session, slot_id: int):
        active_entries = db.query(WaitlistEntry).filter(
            and_(
                WaitlistEntry.slot_id == slot_id,
                WaitlistEntry.status.in_([
                    WaitlistStatus.PENDING,
                    WaitlistStatus.NOTIFIED,
                ]),
            )
        ).order_by(
            WaitlistEntry.priority_score.desc(),
            WaitlistEntry.created_at.asc(),
        ).all()

        for idx, entry in enumerate(active_entries):
            entry.queue_position = idx + 1

    def _calculate_estimated_opportunity(
        self,
        db: Session,
        slot_id: int,
        current_position: int,
    ) -> float:
        slot = db.query(CourseSlot).filter(CourseSlot.id == slot_id).first()
        if not slot or current_position <= 0:
            return 0.0

        historical_release_rate = 0.15
        available_slots = max(0, slot.capacity - slot.enrolled_count)
        base_opportunity = min(1.0, (available_slots + 1) / max(current_position, 1))
        adjusted = base_opportunity * (1 + historical_release_rate)
        return round(min(1.0, adjusted), 4)

    def _calculate_average_wait_time(
        self,
        db: Session,
        store_id: Optional[int] = None,
    ) -> float:
        enrolled_entries = db.query(WaitlistEntry).join(CourseSlot).join(Course).filter(
            WaitlistEntry.status.in_([
                WaitlistStatus.CONFIRMED,
                WaitlistStatus.ENROLLED,
                WaitlistStatus.ATTENDED,
            ]),
            WaitlistEntry.created_at.isnot(None),
            WaitlistEntry.confirmed_at.isnot(None),
        )

        if store_id:
            enrolled_entries = enrolled_entries.filter(Course.store_id == store_id)

        enrolled_entries = enrolled_entries.all()

        if not enrolled_entries:
            return 0.0

        total_hours = 0.0
        for e in enrolled_entries:
            if e.created_at and e.confirmed_at:
                delta = e.confirmed_at - e.created_at
                total_hours += delta.total_seconds() / 3600

        return round(total_hours / len(enrolled_entries), 2)

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
        waitlist_case = case(
            (WaitlistEntry.status.notin_([WaitlistStatus.CANCELLED]), WaitlistEntry.id),
            else_=None
        )
        confirmed_case = case(
            (
                WaitlistEntry.status.in_([
                    WaitlistStatus.CONFIRMED,
                    WaitlistStatus.ATTENDED,
                    WaitlistStatus.NO_SHOW,
                ]),
                WaitlistEntry.id,
            ),
            else_=None
        )
        enrolled_case = case(
            (WaitlistEntry.status == WaitlistStatus.ENROLLED, WaitlistEntry.id),
            else_=None
        )
        attended_case = case(
            (WaitlistEntry.status == WaitlistStatus.ATTENDED, WaitlistEntry.id),
            else_=None
        )
        no_show_case = case(
            (WaitlistEntry.status == WaitlistStatus.NO_SHOW, WaitlistEntry.id),
            else_=None
        )

        query = db.query(
            Store.id,
            Store.name,
            func.count(func.distinct(Course.id)).label("total_courses"),
            func.count(func.distinct(waitlist_case)).label("total_waitlist"),
            func.count(func.distinct(confirmed_case)).label("total_confirmed"),
            func.count(func.distinct(enrolled_case)).label("total_enrolled"),
            func.count(func.distinct(attended_case)).label("total_attended"),
            func.count(func.distinct(no_show_case)).label("total_no_show"),
        ).select_from(Store).outerjoin(Course).outerjoin(CourseSlot).outerjoin(
            WaitlistEntry,
            WaitlistEntry.slot_id == CourseSlot.id
        ).group_by(Store.id)

        if store_id:
            query = query.filter(Store.id == store_id)

        results = query.all()

        stats = []
        for row in results:
            total_waitlist = row.total_waitlist or 0
            total_confirmed = row.total_confirmed or 0
            total_attended = row.total_attended or 0
            total_no_show = row.total_no_show or 0
            conversion_rate = (
                total_confirmed / total_waitlist if total_waitlist > 0 else 0.0
            )
            total_marked = total_attended + total_no_show
            attendance_rate = (
                total_attended / total_marked if total_marked > 0 else 0.0
            )
            avg_wait_time = self._calculate_average_wait_time(db, row.id)

            stats.append(StoreConversionResponse(
                store_id=row.id,
                store_name=row.name,
                total_courses=row.total_courses or 0,
                total_waitlist=total_waitlist,
                total_confirmed=total_confirmed,
                total_enrolled=row.total_enrolled or 0,
                total_attended=total_attended,
                total_no_show=total_no_show,
                attendance_rate=round(attendance_rate, 4),
                conversion_rate=round(conversion_rate, 4),
                average_wait_time_hours=avg_wait_time,
            ))

        return stats

    def get_slot_waitlist_dashboard(
        self,
        db: Session,
        slot_id: Optional[int] = None,
        store_id: Optional[int] = None,
        course_id: Optional[int] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> List[SlotWaitlistDashboardResponse]:
        query = db.query(CourseSlot).join(Course).join(Store).filter(
            CourseSlot.is_active == True,
            Course.is_active == True,
            Store.is_active == True,
        )

        if slot_id:
            query = query.filter(CourseSlot.id == slot_id)
        if store_id:
            query = query.filter(Store.id == store_id)
        if course_id:
            query = query.filter(Course.id == course_id)
        if date_from:
            query = query.filter(CourseSlot.start_time >= date_from)
        if date_to:
            query = query.filter(CourseSlot.start_time <= date_to)

        slots = query.order_by(CourseSlot.start_time.asc()).all()

        results = []
        for slot in slots:
            total_waitlist = db.query(WaitlistEntry).filter(
                and_(
                    WaitlistEntry.slot_id == slot.id,
                    WaitlistEntry.status.notin_([WaitlistStatus.CANCELLED]),
                )
            ).count()

            pending_count = db.query(WaitlistEntry).filter(
                and_(
                    WaitlistEntry.slot_id == slot.id,
                    WaitlistEntry.status == WaitlistStatus.PENDING,
                )
            ).count()

            notified_count = db.query(WaitlistEntry).filter(
                and_(
                    WaitlistEntry.slot_id == slot.id,
                    WaitlistEntry.status == WaitlistStatus.NOTIFIED,
                )
            ).count()

            confirmed_count = db.query(WaitlistEntry).filter(
                and_(
                    WaitlistEntry.slot_id == slot.id,
                    WaitlistEntry.status.in_([
                        WaitlistStatus.CONFIRMED,
                        WaitlistStatus.ATTENDED,
                        WaitlistStatus.NO_SHOW,
                    ]),
                )
            ).count()

            declined_count = db.query(WaitlistEntry).filter(
                and_(
                    WaitlistEntry.slot_id == slot.id,
                    WaitlistEntry.status == WaitlistStatus.DECLINED,
                )
            ).count()

            timeout_count = db.query(WaitlistEntry).filter(
                and_(
                    WaitlistEntry.slot_id == slot.id,
                    WaitlistEntry.status == WaitlistStatus.TIMEOUT,
                )
            ).count()

            cancelled_count = db.query(WaitlistEntry).filter(
                and_(
                    WaitlistEntry.slot_id == slot.id,
                    WaitlistEntry.status == WaitlistStatus.CANCELLED,
                )
            ).count()

            attended_count = db.query(WaitlistEntry).filter(
                and_(
                    WaitlistEntry.slot_id == slot.id,
                    WaitlistEntry.status == WaitlistStatus.ATTENDED,
                )
            ).count()

            no_show_count = db.query(WaitlistEntry).filter(
                and_(
                    WaitlistEntry.slot_id == slot.id,
                    WaitlistEntry.status == WaitlistStatus.NO_SHOW,
                )
            ).count()

            available_release = self._calculate_available_release_slots(db, slot)
            total_marked = attended_count + no_show_count
            attendance_rate = round(attended_count / total_marked, 4) if total_marked > 0 else 0.0
            conversion_rate = round(confirmed_count / total_waitlist, 4) if total_waitlist > 0 else 0.0

            results.append(SlotWaitlistDashboardResponse(
                slot_id=slot.id,
                course_id=slot.course_id,
                course_name=slot.course.name,
                store_id=slot.course.store_id,
                store_name=slot.course.store.name,
                slot_start_time=slot.start_time,
                slot_end_time=slot.end_time,
                capacity=slot.capacity,
                enrolled_count=slot.enrolled_count,
                pending_count=pending_count,
                notified_count=notified_count,
                confirmed_count=confirmed_count,
                declined_count=declined_count,
                timeout_count=timeout_count,
                cancelled_count=cancelled_count,
                attended_count=attended_count,
                no_show_count=no_show_count,
                available_release_slots=available_release,
                total_waitlist_count=total_waitlist,
                attendance_rate=attendance_rate,
                conversion_rate=conversion_rate,
            ))

        return results


waitlist_service = WaitlistService()
