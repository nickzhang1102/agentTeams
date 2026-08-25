"""项目菜单使用的运行时配置 API。

配置仍然保存在现有的加密数据库真源中；本路由只改变用户入口，
避免把 LLM/Web Search 凭证暴露在管理后台导航里。读取对所有已登录用户
开放，写入沿用管理员权限，防止普通用户修改全局运行时凭证。
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.deps import get_current_user, get_admin_user
from database import get_db
from models import LLMModel, SystemConfig, User
from api.admin.admin_schemas import SettingUpdateRequest


PROJECT_SETTING_KEYS = ("EXA_API_KEY", "TAVILY_API_KEY")

router = APIRouter(prefix="/api/project", tags=["project-config"])


def _search_settings(db_session: Session) -> list[dict]:
    rows = (
        db_session.query(SystemConfig)
        .filter(SystemConfig.key.in_(PROJECT_SETTING_KEYS))
        .order_by(SystemConfig.key.asc())
        .all()
    )
    by_key = {row.key: row for row in rows}
    # Seed/migration normally creates both rows, but returning an explicit empty
    # state keeps the first-run experience deterministic on a fresh database.
    return [
        (
            by_key[key].to_dict()
            if key in by_key
            else {
                "id": None,
                "key": key,
                "value": "",
                "is_secret": True,
                "is_configured": False,
                "description": f"{key.removesuffix('_API_KEY')} Web Search API Key",
                "created_at": None,
                "updated_at": None,
            }
        )
        for key in PROJECT_SETTING_KEYS
    ]


def _project_model_to_dict(model: LLMModel, *, can_edit: bool) -> dict:
    """Return only the model fields needed by the project settings page.

    Administrators need the endpoint/base URL and test diagnostics to edit and
    troubleshoot a model. Regular users only need the selection/status view;
    internal gateway addresses and upstream error details should not leave the
    admin boundary.
    """
    result = model.to_dict(include_sensitive=can_edit)
    if not can_edit:
        for field in ("base_url", "api_key", "api_key_masked", "last_test_error"):
            result.pop(field, None)
    return result


@router.get("/config")
def get_project_config(
    user: User = Depends(get_current_user),
    db_session: Session = Depends(get_db),
):
    """返回项目设置页所需的脱敏配置概览。"""
    models = (
        db_session.query(LLMModel)
        .order_by(LLMModel.sort_order, LLMModel.id)
        .all()
    )
    can_edit = bool(user.is_admin)
    return {
        "can_edit": can_edit,
        "models": [_project_model_to_dict(model, can_edit=can_edit) for model in models],
        "search_settings": _search_settings(db_session),
    }


@router.put("/config/settings/{key}")
def update_project_setting(
    key: str,
    payload: SettingUpdateRequest,
    db_session: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """更新 Exa/Tavily 密钥；留空保持原密钥。"""
    if key not in PROJECT_SETTING_KEYS:
        raise HTTPException(status_code=404, detail="项目配置不存在")
    row = db_session.query(SystemConfig).filter_by(key=key).first()
    if row is None:
        row = SystemConfig(
            key=key,
            value="",
            description=f"{key.removesuffix('_API_KEY')} Web Search API Key",
        )
        db_session.add(row)

    value = str(payload.value or "")
    if value:
        row.value = value
    db_session.commit()
    db_session.refresh(row)
    return {"setting": row.to_dict()}


# LLM model CRUD/test routes are intentionally mounted outside /api/admin too.
# Their original dependency still requires an administrator, while the project
# page becomes the single user-facing configuration entry.
from api.admin.llm_model_admin_api import router as llm_model_router  # noqa: E402

router.include_router(llm_model_router)
