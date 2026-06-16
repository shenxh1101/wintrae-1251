from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import CourseSlot
from app.schemas import CourseSlotCreate, CourseSlotResponse, CourseSlotUpdate
from app.crud import CRUDBase

router = APIRouter(prefix="/slots", tags=["课程时间段"])

crud_slot = CRUDBase[CourseSlot, CourseSlotCreate, CourseSlotUpdate](CourseSlot)


@router.post("", response_model=CourseSlotResponse, summary="创建课程时间段")
def create_slot(slot_in: CourseSlotCreate, db: Session = Depends(get_db)):
    return crud_slot.create(db=db, obj_in=slot_in)


@router.get("", response_model=List[CourseSlotResponse], summary="获取时间段列表")
def get_slots(
    course_id: int = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    query = db.query(CourseSlot)
    if course_id:
        query = query.filter(CourseSlot.course_id == course_id)
    return query.order_by(CourseSlot.start_time).offset(skip).limit(limit).all()


@router.get("/{slot_id}", response_model=CourseSlotResponse, summary="获取时间段详情")
def get_slot(slot_id: int, db: Session = Depends(get_db)):
    slot = crud_slot.get(db=db, id=slot_id)
    if not slot:
        raise HTTPException(status_code=404, detail="Course slot not found")
    return slot


@router.put("/{slot_id}", response_model=CourseSlotResponse, summary="更新时间段信息")
def update_slot(
    slot_id: int,
    slot_in: CourseSlotUpdate,
    db: Session = Depends(get_db),
):
    slot = crud_slot.get(db=db, id=slot_id)
    if not slot:
        raise HTTPException(status_code=404, detail="Course slot not found")
    return crud_slot.update(db=db, db_obj=slot, obj_in=slot_in)


@router.delete("/{slot_id}", summary="删除时间段")
def delete_slot(slot_id: int, db: Session = Depends(get_db)):
    slot = crud_slot.get(db=db, id=slot_id)
    if not slot:
        raise HTTPException(status_code=404, detail="Course slot not found")
    crud_slot.remove(db=db, id=slot_id)
    return {"message": "Course slot deleted successfully"}
