from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Student
from app.schemas import StudentCreate, StudentResponse, StudentUpdate
from app.crud import CRUDBase

router = APIRouter(prefix="/students", tags=["学员管理"])

crud_student = CRUDBase[Student, StudentCreate, StudentUpdate](Student)


@router.post("", response_model=StudentResponse, summary="创建学员")
def create_student(student_in: StudentCreate, db: Session = Depends(get_db)):
    existing = db.query(Student).filter(Student.phone == student_in.phone).first()
    if existing:
        raise HTTPException(status_code=400, detail="Phone number already registered")
    return crud_student.create(db=db, obj_in=student_in)


@router.get("", response_model=List[StudentResponse], summary="获取学员列表")
def get_students(
    phone: str = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    query = db.query(Student)
    if phone:
        query = query.filter(Student.phone.like(f"%{phone}%"))
    return query.offset(skip).limit(limit).all()


@router.get("/{student_id}", response_model=StudentResponse, summary="获取学员详情")
def get_student(student_id: int, db: Session = Depends(get_db)):
    student = crud_student.get(db=db, id=student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    return student


@router.get("/phone/{phone}", response_model=StudentResponse, summary="通过手机号查询学员")
def get_student_by_phone(phone: str, db: Session = Depends(get_db)):
    student = db.query(Student).filter(Student.phone == phone).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    return student


@router.put("/{student_id}", response_model=StudentResponse, summary="更新学员信息")
def update_student(
    student_id: int,
    student_in: StudentUpdate,
    db: Session = Depends(get_db),
):
    student = crud_student.get(db=db, id=student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    return crud_student.update(db=db, db_obj=student, obj_in=student_in)


@router.delete("/{student_id}", summary="删除学员")
def delete_student(student_id: int, db: Session = Depends(get_db)):
    student = crud_student.get(db=db, id=student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    crud_student.remove(db=db, id=student_id)
    return {"message": "Student deleted successfully"}
