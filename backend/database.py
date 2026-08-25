"""
数据库会话管理模块

提供 FastAPI 兼容的会话依赖注入。
"""
from typing import Generator

from sqlalchemy.orm import Session

from db import SessionLocal


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI 依赖注入：获取数据库会话

    用法：
        @router.get("/")
        async def endpoint(db: Session = Depends(get_db)):
            ...

    会话在请求结束后自动关闭。
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()