from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Store
from app.schemas import StoreCreate, StoreResponse, StoreUpdate
from app.crud import CRUDBase

router = APIRouter(prefix="/stores", tags=["门店管理"])

crud_store = CRUDBase[Store, StoreCreate, StoreUpdate](Store)


@router.post("", response_model=StoreResponse, summary="创建门店")
def create_store(store_in: StoreCreate, db: Session = Depends(get_db)):
    return crud_store.create(db=db, obj_in=store_in)


@router.get("", response_model=List[StoreResponse], summary="获取门店列表")
def get_stores(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud_store.get_multi(db=db, skip=skip, limit=limit)


@router.get("/{store_id}", response_model=StoreResponse, summary="获取门店详情")
def get_store(store_id: int, db: Session = Depends(get_db)):
    store = crud_store.get(db=db, id=store_id)
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    return store


@router.put("/{store_id}", response_model=StoreResponse, summary="更新门店信息")
def update_store(
    store_id: int,
    store_in: StoreUpdate,
    db: Session = Depends(get_db),
):
    store = crud_store.get(db=db, id=store_id)
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    return crud_store.update(db=db, db_obj=store, obj_in=store_in)


@router.delete("/{store_id}", summary="删除门店")
def delete_store(store_id: int, db: Session = Depends(get_db)):
    store = crud_store.get(db=db, id=store_id)
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    crud_store.remove(db=db, id=store_id)
    return {"message": "Store deleted successfully"}
