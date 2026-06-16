from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Course
from app.schemas import CourseCreate, CourseResponse, CourseUpdate
from app.crud import CRUDBase

router = APIRouter(prefix="/courses", tags=["课程管理"])

crud_course = CRUDBase[Course, CourseCreate, CourseUpdate](Course)


@router.post("", response_model=CourseResponse, summary="创建课程")
def create_course(course_in: CourseCreate, db: Session = Depends(get_db)):
    return crud_course.create(db=db, obj_in=course_in)


@router.get("", response_model=List[CourseResponse], summary="获取课程列表")
def get_courses(
    store_id: int = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    query = db.query(Course)
    if store_id:
        query = query.filter(Course.store_id == store_id)
    return query.offset(skip).limit(limit).all()


@router.get("/{course_id}", response_model=CourseResponse, summary="获取课程详情")
def get_course(course_id: int, db: Session = Depends(get_db)):
    course = crud_course.get(db=db, id=course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    return course


@router.put("/{course_id}", response_model=CourseResponse, summary="更新课程信息")
def update_course(
    course_id: int,
    course_in: CourseUpdate,
    db: Session = Depends(get_db),
):
    course = crud_course.get(db=db, id=course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    return crud_course.update(db=db, db_obj=course, obj_in=course_in)


@router.delete("/{course_id}", summary="删除课程")
def delete_course(course_id: int, db: Session = Depends(get_db)):
    course = crud_course.get(db=db, id=course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    crud_course.remove(db=db, id=course_id)
    return {"message": "Course deleted successfully"}
