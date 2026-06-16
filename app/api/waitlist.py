from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import WaitlistStatus
from app.schemas import (
    WaitlistEntryCreate,
    WaitlistEntryCancel,
    WaitlistEntryConfirm,
    WaitlistEntryResponse,
    WaitlistPositionResponse,
    SlotReleaseRequest,
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


@router.post("/process-timeouts", summary="处理超时未确认的候补")
def process_timeouts(db: Session = Depends(get_db)):
    processed = waitlist_service.process_timeouts(db=db)
    return {
        "message": f"Processed {len(processed)} timeout entries",
        "processed_count": len(processed),
        "processed_entries": processed,
    }
