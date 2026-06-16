from typing import List, Optional
from datetime import datetime
from io import StringIO
import csv
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
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


@router.get("/slots/dashboard/export.csv", summary="导出时间段候补看板CSV")
def export_slot_dashboard_csv(
    slot_id: Optional[int] = Query(None, description="按时间段ID过滤"),
    store_id: Optional[int] = Query(None, description="按门店过滤"),
    course_id: Optional[int] = Query(None, description="按课程过滤"),
    date_from: Optional[datetime] = Query(None, description="开始日期（含）"),
    date_to: Optional[datetime] = Query(None, description="结束日期（含）"),
    db: Session = Depends(get_db),
):
    dashboard = waitlist_service.get_slot_waitlist_dashboard(
        db=db,
        slot_id=slot_id,
        store_id=store_id,
        course_id=course_id,
        date_from=date_from,
        date_to=date_to,
    )

    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "时间段ID", "课程ID", "课程名称", "门店ID", "门店名称",
        "开始时间", "结束时间", "容量", "已报名人数", "排队中人数",
        "已通知人数", "已确认人数", "已放弃人数", "已超时人数",
        "已取消人数", "已到课人数", "未到课人数", "剩余可释放名额", "候补总人数"
    ])

    for d in dashboard:
        writer.writerow([
            d.slot_id,
            d.course_id,
            d.course_name,
            d.store_id,
            d.store_name,
            d.slot_start_time.strftime("%Y-%m-%d %H:%M:%S"),
            d.slot_end_time.strftime("%Y-%m-%d %H:%M:%S"),
            d.capacity,
            d.enrolled_count,
            d.pending_count,
            d.notified_count,
            d.confirmed_count,
            d.declined_count,
            d.timeout_count,
            d.cancelled_count,
            d.attended_count,
            d.no_show_count,
            d.available_release_slots,
            d.total_waitlist_count,
        ])

    buffer.seek(0)
    filename = f"waitlist_dashboard_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv; charset=utf-8-sig",
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
        },
    )
