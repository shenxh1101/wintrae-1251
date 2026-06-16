from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    WaitlistStatus,
    AttendanceStatus,
    PriorityConfig,
    WaitlistEntry,
)
from app.schemas import (
    WaitlistEntryCreate,
    WaitlistEntryCancel,
    WaitlistEntryConfirm,
    WaitlistEntryResponse,
    WaitlistPositionResponse,
    WaitlistPreviewResponse,
    SlotReleaseRequest,
    TimeoutProcessRequest,
    AttendanceMarkRequest,
    BatchAttendanceRequest,
    AttendanceRosterResponse,
    WaitlistUrgentUpdate,
    PriorityConfigCreate,
    PriorityConfigUpdate,
    PriorityConfigResponse,
)
from app.services.waitlist_service import waitlist_service

router = APIRouter(prefix="/waitlist", tags=["候补管理"])


@router.post("", response_model=WaitlistEntryResponse, summary="提交候补申请")
def create_waitlist(
    entry_in: WaitlistEntryCreate,
    db: Session = Depends(get_db),
):
    try:
        db.begin_nested()
        result = waitlist_service.create_waitlist_entry(db=db, entry_in=entry_in)
        db.commit()
        return result
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@router.post("/preview", response_model=WaitlistPreviewResponse, summary="候补提交前预览排位")
def preview_waitlist_position(
    slot_id: int = Query(..., description="时间段ID"),
    student_id: int = Query(..., description="学员ID"),
    is_urgent: bool = Query(False, description="是否加急"),
    db: Session = Depends(get_db),
):
    try:
        return waitlist_service.preview_waitlist_position(
            db=db, slot_id=slot_id, student_id=student_id, is_urgent=is_urgent
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{entry_id}", response_model=WaitlistEntryResponse, summary="取消候补")
def cancel_waitlist(
    entry_id: int,
    student_id: int,
    cancel_in: WaitlistEntryCancel,
    db: Session = Depends(get_db),
):
    try:
        return waitlist_service.cancel_waitlist_entry(
            db=db,
            entry_id=entry_id,
            student_id=student_id,
            cancel_reason=cancel_in.cancel_reason,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{entry_id}/position", response_model=WaitlistPositionResponse, summary="查询候补排位与预计机会")
def get_waitlist_position(
    entry_id: int,
    db: Session = Depends(get_db),
):
    try:
        return waitlist_service.get_waitlist_position(db=db, entry_id=entry_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/student/{student_id}", response_model=List[WaitlistEntryResponse], summary="查询学员的所有候补")
def get_student_waitlists(
    student_id: int,
    status: Optional[WaitlistStatus] = Query(None, description="候补状态过滤"),
    db: Session = Depends(get_db),
):
    return waitlist_service.get_student_waitlists(
        db=db, student_id=student_id, status=status
    )


@router.post("/release", summary="释放名额并通知候补学员")
def release_slots(
    release_in: SlotReleaseRequest,
    db: Session = Depends(get_db),
):
    try:
        notified = waitlist_service.release_slot(
            db=db,
            slot_id=release_in.slot_id,
            release_count=release_in.release_count,
        )
        notified_list = []
        for e in notified:
            notified_list.append({
                "id": e.id,
                "entry_id": e.id,
                "slot_id": e.slot_id,
                "student_id": e.student_id,
                "status": e.status.value if hasattr(e.status, "value") else str(e.status),
                "queue_position": e.queue_position,
                "priority_score": e.priority_score,
                "notified_at": e.notified_at.isoformat() if e.notified_at else None,
                "timeout_at": e.timeout_at.isoformat() if e.timeout_at else None,
            })
        return {
            "message": f"Successfully notified {len(notified)} students",
            "notified_count": len(notified),
            "notified_entries": notified_list,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{entry_id}/confirm", response_model=WaitlistEntryResponse, summary="确认或放弃补位")
def confirm_waitlist(
    entry_id: int,
    confirm_in: WaitlistEntryConfirm,
    db: Session = Depends(get_db),
):
    try:
        return waitlist_service.confirm_waitlist(
            db=db,
            entry_id=entry_id,
            confirmed=confirm_in.confirmed,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/process-timeouts", summary="处理超时未确认的候补（支持模拟时间推进）")
def process_timeouts(
    timeout_in: Optional[TimeoutProcessRequest] = None,
    db: Session = Depends(get_db),
):
    simulate_time = None
    slot_id = None
    if timeout_in:
        simulate_time = timeout_in.simulate_time
        slot_id = timeout_in.slot_id

    processed = waitlist_service.process_timeouts(
        db=db,
        simulate_time=simulate_time,
        slot_id=slot_id,
    )
    return {
        "message": f"Processed {len(processed)} timeout entries",
        "processed_count": len(processed),
        "processed_entries": processed,
        "simulate_time_used": simulate_time.isoformat() if simulate_time else None,
    }


@router.post("/{entry_id}/attendance", response_model=WaitlistEntryResponse, summary="标记到课状态")
def mark_attendance(
    entry_id: int,
    mark_in: AttendanceMarkRequest,
    db: Session = Depends(get_db),
):
    try:
        return waitlist_service.mark_attendance(
            db=db,
            entry_id=entry_id,
            attendance_status=mark_in.attendance_status,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/attendance/batch", summary="批量标记到课状态")
def batch_mark_attendance(
    batch_in: BatchAttendanceRequest,
    db: Session = Depends(get_db),
):
    try:
        return waitlist_service.batch_mark_attendance(
            db=db,
            slot_id=batch_in.slot_id,
            attended_ids=batch_in.attended_ids,
            no_show_ids=batch_in.no_show_ids,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/attendance/roster", response_model=AttendanceRosterResponse, summary="门店点名清单（已确认补位学员）")
def get_attendance_roster(
    store_id: Optional[int] = Query(None, description="门店ID过滤"),
    course_id: Optional[int] = Query(None, description="课程ID过滤"),
    slot_id: Optional[int] = Query(None, description="时间段ID过滤"),
    date_from: Optional[datetime] = Query(None, description="开始日期（含）"),
    date_to: Optional[datetime] = Query(None, description="结束日期（含）"),
    db: Session = Depends(get_db),
):
    return waitlist_service.get_attendance_roster(
        db=db,
        store_id=store_id,
        course_id=course_id,
        slot_id=slot_id,
        date_from=date_from,
        date_to=date_to,
    )


@router.put("/{entry_id}/urgent", response_model=WaitlistEntryResponse, summary="设置/取消候补加急")
def set_waitlist_urgent(
    entry_id: int,
    urgent_in: WaitlistUrgentUpdate,
    db: Session = Depends(get_db),
):
    try:
        return waitlist_service.set_urgent(
            db=db,
            entry_id=entry_id,
            is_urgent=urgent_in.is_urgent,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/priority-config", response_model=PriorityConfigResponse, summary="创建课程优先级配置")
def create_priority_config(
    config_in: PriorityConfigCreate,
    db: Session = Depends(get_db),
):
    existing = db.query(PriorityConfig).filter(
        PriorityConfig.course_id == config_in.course_id
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Priority config already exists for this course, use PUT to update")

    config = PriorityConfig(
        course_id=config_in.course_id,
        member_level_score_normal=config_in.member_level_score_normal,
        member_level_score_silver=config_in.member_level_score_silver,
        member_level_score_gold=config_in.member_level_score_gold,
        member_level_score_platinum=config_in.member_level_score_platinum,
        returning_student_bonus=config_in.returning_student_bonus,
        urgent_bonus=config_in.urgent_bonus,
        is_active=True,
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    return config


@router.get("/priority-config/{course_id}", response_model=PriorityConfigResponse, summary="获取课程优先级配置")
def get_priority_config(
    course_id: int,
    db: Session = Depends(get_db),
):
    config = db.query(PriorityConfig).filter(
        PriorityConfig.course_id == course_id
    ).first()
    if not config:
        raise HTTPException(status_code=404, detail="Priority config not found for this course")
    return config


@router.put("/priority-config/{course_id}", response_model=PriorityConfigResponse, summary="更新课程优先级配置")
def update_priority_config(
    course_id: int,
    config_in: PriorityConfigUpdate,
    db: Session = Depends(get_db),
):
    config = db.query(PriorityConfig).filter(
        PriorityConfig.course_id == course_id
    ).first()
    if not config:
        raise HTTPException(status_code=404, detail="Priority config not found for this course")

    update_data = config_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(config, field, value)

    active_entries = db.query(WaitlistEntry).filter(
        WaitlistEntry.status.in_([WaitlistStatus.PENDING, WaitlistStatus.NOTIFIED]),
    ).join(
        PriorityConfig,
        PriorityConfig.course_id == course_id,
        isouter=True,
    ).all()

    db.commit()
    db.refresh(config)
    return config
