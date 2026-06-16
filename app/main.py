from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import engine, Base
from app.api import stores, courses, slots, students, waitlist, notifications, stats


def init_db():
    Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="课程候补与补位通知系统",
    description="线下培训机构热门课程候补与补位通知管理后端服务",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_prefix = settings.API_V1_PREFIX

app.include_router(stores.router, prefix=api_prefix)
app.include_router(courses.router, prefix=api_prefix)
app.include_router(slots.router, prefix=api_prefix)
app.include_router(students.router, prefix=api_prefix)
app.include_router(waitlist.router, prefix=api_prefix)
app.include_router(notifications.router, prefix=api_prefix)
app.include_router(stats.router, prefix=api_prefix)


@app.get("/", summary="根路径 - 健康检查")
async def root():
    return {
        "service": "课程候补与补位通知系统",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health", summary="健康检查")
async def health_check():
    return {"status": "healthy"}
