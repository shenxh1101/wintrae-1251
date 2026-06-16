from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import WaitlistStatus, AttendanceStatus
from app.schemas import (
    WaitlistEntryCreate,
    WaitlistEntryCancel,
    WaitlistEntryConfirm,
    WaitlistEntryResponse,
    WaitlistPositionResponse,
    SlotReleaseRequest,
    TimeoutProcessRequest,
    AttendanceMarkRequest,
    WaitlistUrgentUpdate,
)
from app.services.waitlist_service import waitlist_service

router = APIRouter(prefix="/waitlist", tags=["候补管理"])


@router.post("", response_model=WaitlistEntryResponse, summary="提交候补申请")
def create_waitlist(
    entry_in: WaitlistEntryCreate,
    db: Session = Depends(get_db),
):
    try:
        return waitlist_service.create_waitlist_entry(db=db, entry_in=entry_in)
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
        return {
            "message": f"Successfully notified {len(notified)} students",
            "notified_count": len(notified),
            "notified_entries": notified,
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
