"""LLM 模型公开列表 API

提供给前端用户选择可用模型的列表。
仅返回 is_enabled=true 的模型，不含 api_key/base_url。
"""
import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.deps import get_current_user
from database import get_db
from models import LLMModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/llm-models", tags=["llm-models"])


@router.get("")
async def list_enabled_models(user=Depends(get_current_user), db: Session = Depends(get_db)):
    """获取可用的 LLM 模型列表（仅启用的模型）"""
    models = (
        db.query(LLMModel)
        .filter(LLMModel.is_enabled == True)
        .order_by(LLMModel.sort_order, LLMModel.id)
        .all()
    )

    # 查找默认模型
    default_model = next(
        (m.model_id for m in models if m.is_default),
        models[0].model_id if models else None,
    )

    return {
        "models": [
            {
                "model_id": m.model_id,
                "display_name": m.display_name,
                "context_limit": m.context_limit,
                "max_output_tokens": m.max_output_tokens,
                "provider": m.provider,
                "last_test_ok": m.last_test_ok,
            }
            for m in models
        ],
        "default_model": default_model,
    }
