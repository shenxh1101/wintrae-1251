from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import (
    CoursePopularityResponse,
    StoreConversionResponse,
    SlotWaitlistDashboardResponse,
)
from app.services.waitlist_service import waitlist_service

router = APIRouter(prefix="/stats", tags=["统计分析"])


@router.get("/courses/popularity", response_model=List[CoursePopularityResponse], summary="课程候补热度排行")
def get_course_popularity_ranking(
    store_id: Optional[int] = Query(None, description="按门店过滤"),
    limit: int = Query(20, ge=1, le=100, description="返回数量限制"),
    db: Session = Depends(get_db),
):
    return waitlist_service.get_course_popularity_ranking(
        db=db, store_id=store_id, limit=limit
    )


@router.get("/stores/conversion", response_model=List[StoreConversionResponse], summary="按门店查看转化情况")
def get_store_conversion_stats(
    store_id: Optional[int] = Query(None, description="指定门店ID，不填则返回所有门店"),
    db: Session = Depends(get_db),
):
    return waitlist_service.get_store_conversion_stats(
        db=db, store_id=store_id
    )


@router.get("/slots/dashboard", response_model=List[SlotWaitlistDashboardResponse], summary="课程时间段候补看板")
def get_slot_waitlist_dashboard(
    slot_id: Optional[int] = Query(None, description="按时间段ID过滤"),
    store_id: Optional[int] = Query(None, description="按门店过滤"),
    course_id: Optional[int] = Query(None, description="按课程过滤"),
    date_from: Optional[datetime] = Query(None, description="开始日期（含）"),
    date_to: Optional[datetime] = Query(None, description="结束日期（含）"),
    db: Session = Depends(get_db),
):
    return waitlist_service.get_slot_waitlist_dashboard(
        db=db,
        slot_id=slot_id,
        store_id=store_id,
        course_id=course_id,
        date_from=date_from,
        date_to=date_to,
    )
