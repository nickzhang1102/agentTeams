"""Admin LLM 模型管理路由

提供 LLM 模型的 CRUD 操作和连通性测试。
所有端点需要管理员权限。
"""
import asyncio
import time
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from api.deps import get_admin_user
from db import db
from models import LLMModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/llm-models", tags=["admin-llm-models"])


# ==================== 请求模型 ====================

class LLMModelCreateRequest(BaseModel):
    model_id: str = Field(..., min_length=1, max_length=100)
    display_name: str = Field(..., min_length=1, max_length=200)
    base_url: str = Field(..., min_length=1, max_length=500)
    api_key: str = Field(..., min_length=1, max_length=500)
    context_limit: int = Field(default=128000, ge=1)
    max_output_tokens: int = Field(default=32768, ge=1)
    provider: Optional[str] = Field(default=None, max_length=100)
    is_enabled: bool = Field(default=True)
    is_default: bool = Field(default=False)
    sort_order: int = Field(default=0, ge=0)


class LLMModelUpdateRequest(BaseModel):
    display_name: Optional[str] = Field(default=None, max_length=200)
    base_url: Optional[str] = Field(default=None, max_length=500)
    api_key: Optional[str] = Field(default=None, max_length=500)  # 空字符串不更新
    context_limit: Optional[int] = Field(default=None, ge=1)
    max_output_tokens: Optional[int] = Field(default=None, ge=1)
    provider: Optional[str] = Field(default=None, max_length=100)
    is_enabled: Optional[bool] = None
    is_default: Optional[bool] = None
    sort_order: Optional[int] = Field(default=None, ge=0)


# ==================== 路由 ====================

@router.get("")
async def list_models(admin=Depends(get_admin_user)):
    """获取所有 LLM 模型列表（含禁用模型，api_key 脱敏）"""
    models = db.query(LLMModel).order_by(LLMModel.sort_order, LLMModel.id).all()
    return {"models": [m.to_dict(include_sensitive=True) for m in models]}


@router.post("", status_code=201)
async def create_model(req: LLMModelCreateRequest, admin=Depends(get_admin_user)):
    """创建 LLM 模型"""
    # 检查 model_id 唯一性
    existing = db.query(LLMModel).filter(LLMModel.model_id == req.model_id).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"模型 '{req.model_id}' 已存在")

    model = LLMModel(
        model_id=req.model_id,
        display_name=req.display_name,
        base_url=req.base_url,
        api_key=req.api_key,
        context_limit=req.context_limit,
        max_output_tokens=req.max_output_tokens,
        provider=req.provider,
        is_enabled=req.is_enabled,
        is_default=req.is_default,
        sort_order=req.sort_order,
    )

    # 如果设为默认，取消其他默认
    if req.is_default:
        _clear_default_model()

    db.add(model)
    db.commit()
    db.refresh(model)
    _invalidate_model_cache()
    return model.to_dict(include_sensitive=True)


@router.put("/{model_id}")
async def update_model(model_id: int, req: LLMModelUpdateRequest, admin=Depends(get_admin_user)):
    """更新 LLM 模型"""
    model = db.get(LLMModel, model_id)
    if not model:
        raise HTTPException(status_code=404, detail="模型不存在")

    update_data = req.model_dump(exclude_unset=True)

    # api_key 为空字符串时不更新
    if 'api_key' in update_data and not update_data['api_key']:
        del update_data['api_key']

    # 设为默认时取消其他默认
    if update_data.get('is_default'):
        _clear_default_model()

    for key, value in update_data.items():
        setattr(model, key, value)

    db.commit()
    db.refresh(model)
    _invalidate_model_cache()
    return model.to_dict(include_sensitive=True)


@router.delete("/{model_id}")
async def delete_model(model_id: int, admin=Depends(get_admin_user)):
    """删除 LLM 模型"""
    model = db.get(LLMModel, model_id)
    if not model:
        raise HTTPException(status_code=404, detail="模型不存在")

    if model.is_default:
        raise HTTPException(status_code=400, detail="不能删除默认模型，请先将其他模型设为默认")

    db.delete(model)
    db.commit()
    _invalidate_model_cache()
    return {"message": "已删除"}


@router.post("/{model_id}/test")
async def test_model(model_id: int, admin=Depends(get_admin_user)):
    """测试 LLM 模型连通性"""
    model = db.get(LLMModel, model_id)
    if not model:
        raise HTTPException(status_code=404, detail="模型不存在")

    # 用 asyncio.to_thread 包装同步阻塞调用，避免阻塞事件循环
    result = await asyncio.to_thread(_test_model_connection, model)

    # 更新测试结果到 DB
    model.last_test_at = datetime.now(timezone.utc)
    model.last_test_ok = result['ok']
    model.last_test_error = result.get('error')
    db.commit()

    return result


# ==================== 内部工具 ====================

def _clear_default_model():
    """取消所有模型的默认标记"""
    for m in db.query(LLMModel).filter(LLMModel.is_default == True).all():
        m.is_default = False


def _extract_error_detail(e: Exception) -> str:
    """从 OpenAI SDK 异常中提取详细错误信息"""
    # 优先提取 OpenAI APIStatusError 的 response body
    if hasattr(e, 'response') and e.response is not None:
        try:
            body = e.response.text
            if body:
                return f"{e} | body: {body[:300]}"
        except Exception:
            pass
    # 提取 httpx/httpcore 错误体
    if hasattr(e, 'body') and e.body:
        try:
            return f"{e} | error_body: {str(e.body)[:300]}"
        except Exception:
            pass
    return str(e)


def _test_model_connection(model: LLMModel) -> dict:
    """测试单个模型的连通性，返回 {ok, latency_ms, model, error?}

    修复要点：
    1. max_tokens=16（原 1 太小，部分国产模型网关会拒绝或返回异常状态码）
    2. timeout=30（原 15 太短，与 LLMService 保持一致，避免冷启动超时）
    3. 404 时回退调用 models.list() 区分"端点不通"和"模型名错误"
    4. 错误信息提取 response body，帮助排查
    """
    from openai import OpenAI

    start = time.time()
    try:
        client = OpenAI(
            api_key=model.api_key,
            base_url=model.base_url,
            timeout=30,
        )
        # 发一次最简请求，max_tokens=16 兼容所有模型
        response = client.chat.completions.create(
            model=model.model_id,
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=16,
        )
        latency_ms = int((time.time() - start) * 1000)
        return {"ok": True, "latency_ms": latency_ms, "model": model.model_id}
    except Exception as e:
        latency_ms = int((time.time() - start) * 1000)
        error_msg = _extract_error_detail(e)

        # 404 时回退探测：尝试 models.list() 区分端点问题 vs 模型名问题
        status_code = getattr(e, 'status_code', None)
        if status_code == 404:
            try:
                client.models.list()
                # 端点可达但模型名不对
                error_msg = f"端点可达但模型名 '{model.model_id}' 不存在（404）。请检查 model_id 是否正确。原始错误: {error_msg}"
            except Exception as list_err:
                list_detail = _extract_error_detail(list_err)
                error_msg = f"端点不可达（404）。models.list() 也失败: {list_detail[:200]}"

        # 截断过长的错误信息
        if len(error_msg) > 500:
            error_msg = error_msg[:500] + "..."
        return {"ok": False, "latency_ms": latency_ms, "model": model.model_id, "error": error_msg}


def _invalidate_model_cache():
    """清除 LLMService 的模型配置缓存"""
    try:
        from services.llm_service import invalidate_model_cache
        invalidate_model_cache()
    except Exception:
        pass


def health_check_all_models(session=None):
    """探活所有启用的模型，更新 last_test_* 字段。供后台调度调用。

    Args:
        session: 可选的独立 DB Session。后台线程应传入专属 Session 避免与主线程共享
                 scoped_session。为 None 时使用全局 db（兼容管理端手动触发）。
    """
    _db = session if session is not None else db
    models = _db.query(LLMModel).filter(LLMModel.is_enabled == True).all()
    now = datetime.now(timezone.utc)

    for model in models:
        result = _test_model_connection(model)
        model.last_test_at = now
        model.last_test_ok = result['ok']
        model.last_test_error = result.get('error')
        logger.info(
            "Health check: %s → %s (%dms)",
            model.model_id, "OK" if result['ok'] else result.get('error', 'FAIL'), result['latency_ms']
        )

    _db.commit()
    _invalidate_model_cache()