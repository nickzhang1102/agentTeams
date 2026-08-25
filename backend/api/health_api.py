"""
健康检查端点

提供 /health（存活检查）和 /ready（依赖检查）端点，
用于 Docker 部署、负载均衡和监控系统。
"""
import time
import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.deps import get_db
from config import Config

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])

# 应用启动时间
_start_time = time.time()


@router.get("/health")
@router.get("/api/health")
async def health_check():
    """存活检查 - 仅确认进程在运行。

    ``/health`` is used by the backend/container healthcheck while
    ``/api/health`` is the browser-facing path behind the frontend proxy.
    Both paths intentionally expose the same payload.
    """
    return {
        "status": "ok",
        "version": Config.APP_VERSION,
        "uptime": round(time.time() - _start_time, 1)
    }


@router.get("/ready")
async def readiness_check(db_session: Session = Depends(get_db)):
    """就绪检查 - 验证关键依赖可用

    检查项：
    1. 数据库连接
    2. LLM API 配置
    """
    checks = {}
    overall_ready = True

    # 1. 数据库连接
    try:
        db_session.execute(text("SELECT 1"))
        checks["database"] = {"status": "ok"}
    except Exception as e:
        # /ready 为公开端点，异常细节只进日志，不回显给外部
        logger.error(f"Readiness check failed (database): {e}", exc_info=True)
        checks["database"] = {"status": "error", "detail": "数据库连接失败"}
        overall_ready = False

    # 2. LLM API 配置
    try:
        from models import LLMModel
        model = (
            db_session.query(LLMModel)
            .filter(LLMModel.is_enabled == True)
            .order_by(LLMModel.is_default.desc(), LLMModel.sort_order, LLMModel.id)
            .first()
        )
        if model and model.api_key and model.base_url:
            checks["llm_config"] = {"status": "ok"}
        else:
            checks["llm_config"] = {
                "status": "warning",
                "detail": "No enabled LLM model is configured in the admin database",
            }
    except Exception as e:
        logger.error(f"Readiness check failed (llm_config): {e}", exc_info=True)
        checks["llm_config"] = {"status": "error", "detail": "LLM 配置检查失败"}
        overall_ready = False

    status_code = 200 if overall_ready else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ready" if overall_ready else "not_ready",
            "checks": checks
        }
    )
