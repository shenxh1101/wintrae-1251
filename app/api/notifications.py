from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import NotificationType, NotificationStatus, NotificationChannel
from app.schemas import (
    NotificationResponse,
    NotificationDeliveryReceipt,
    NotificationReadReceipt,
)
from app.services.notification_service import notification_service

router = APIRouter(prefix="/notifications", tags=["通知查询"])


@router.get("/{notification_id}", response_model=NotificationResponse, summary="获取通知详情（含完整时间线）")
def get_notification(
    notification_id: int,
    db: Session = Depends(get_db),
):
    full_notification = notification_service.get_notification_with_timeline(
        db=db, notification_id=notification_id
    )
    if not full_notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    result = full_notification["notification"]
    result.attempts = full_notification["attempts"]
    result.timeline = full_notification["timeline"]
    return result


@router.post("/{notification_id}/delivery-receipt", response_model=NotificationResponse, summary="上报通知送达回执")
def report_delivery_receipt(
    notification_id: int,
    receipt_in: NotificationDeliveryReceipt,
    db: Session = Depends(get_db),
):
    result = notification_service.process_delivery_receipt(
        db=db,
        notification_id=notification_id,
        channel=receipt_in.channel,
        delivered=receipt_in.delivered,
        error_message=receipt_in.error_message,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Notification not found")
    return result


@router.post("/{notification_id}/read-receipt", response_model=NotificationResponse, summary="上报通知已读回执")
def report_read_receipt(
    notification_id: int,
    receipt_in: NotificationReadReceipt,
    db: Session = Depends(get_db),
):
    result = notification_service.process_read_receipt(
        db=db,
        notification_id=notification_id,
        channel=receipt_in.channel,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Notification not found")
    return result


@router.get("/waitlist/{waitlist_entry_id}", response_model=List[NotificationResponse], summary="查询候补记录的通知历史")
def get_notifications_by_waitlist(
    waitlist_entry_id: int,
    notification_type: Optional[NotificationType] = Query(None, description="通知类型过滤"),
    status: Optional[NotificationStatus] = Query(None, description="通知状态过滤"),
    db: Session = Depends(get_db),
):
    notifications = notification_service.get_notifications_by_waitlist(
        db=db,
        waitlist_entry_id=waitlist_entry_id,
        notification_type=notification_type,
        status=status,
    )
    results = []
    for n in notifications:
        full = notification_service.get_notification_with_timeline(db, n.id)
        if full:
            n.attempts = full["attempts"]
            n.timeline = full["timeline"]
        results.append(n)
    return results


@router.get("/student/{student_id}", response_model=List[NotificationResponse], summary="查询学员的通知记录")
def get_notifications_by_student(
    student_id: int,
    notification_type: Optional[NotificationType] = Query(None, description="通知类型过滤"),
    status: Optional[NotificationStatus] = Query(None, description="通知状态过滤"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    return notification_service.get_notifications_by_student(
        db=db,
        student_id=student_id,
        notification_type=notification_type,
        status=status,
        limit=limit,
    )


@router.put("/{notification_id}/read", response_model=NotificationResponse, summary="标记通知已读")
def mark_notification_read(
    notification_id: int,
    db: Session = Depends(get_db),
):
    notification = notification_service.mark_notification_read(
        db=db, notification_id=notification_id
    )
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    return notification


@router.put("/{notification_id}/status", response_model=NotificationResponse, summary="更新通知状态")
def update_notification_status(
    notification_id: int,
    status: NotificationStatus,
    error_message: Optional[str] = None,
    db: Session = Depends(get_db),
):
    notification = notification_service.update_notification_status(
        db=db,
        notification_id=notification_id,
        status=status,
        error_message=error_message,
    )
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    return notification


@router.get("/pending/retry", summary="获取待重试的失败通知列表")
def get_pending_notifications(
    channel: Optional[NotificationChannel] = Query(None, description="通知渠道过滤"),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    notifications = notification_service.get_pending_notifications(
        db=db, channel=channel, limit=limit
    )
    results = []
    for n in notifications:
        results.append({
            "id": n.id,
            "waitlist_entry_id": n.waitlist_entry_id,
            "type": n.type.value if hasattr(n.type, 'value') else str(n.type),
            "channel": n.channel.value if hasattr(n.channel, 'value') else str(n.channel),
            "status": n.status.value if hasattr(n.status, 'value') else str(n.status),
            "attempt_count": n.attempt_count,
            "next_retry_at": n.next_retry_at.isoformat() if n.next_retry_at else None,
            "error_message": n.error_message,
            "sent_at": n.sent_at.isoformat() if n.sent_at else None,
        })
    return {
        "count": len(results),
        "notifications": results,
    }


@router.get("/stats/summary", summary="获取通知统计概览")
def get_notification_stats(
    db: Session = Depends(get_db),
):
    return notification_service.get_notification_stats(db=db)


@router.post("/{notification_id}/retry", response_model=NotificationResponse, summary="重试发送失败的通知")
def retry_notification(
    notification_id: int,
    db: Session = Depends(get_db),
):
    result = notification_service.retry_notification(db=db, notification_id=notification_id)
    if not result:
        raise HTTPException(status_code=404, detail="Notification not found or cannot be retried")
    return result


@router.post("/retry-batch", summary="批量重试待处理的通知")
def retry_pending_notifications(
    limit: int = Query(50, ge=1, le=200, description="批量重试数量限制"),
    db: Session = Depends(get_db),
):
    retried = notification_service.retry_pending_notifications(db=db, limit=limit)
    return {
        "message": f"Retried {len(retried)} notifications",
        "retried_count": len(retried),
        "retried_notifications": retried,
    }
