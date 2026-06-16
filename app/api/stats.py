from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import CoursePopularityResponse, StoreConversionResponse
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
