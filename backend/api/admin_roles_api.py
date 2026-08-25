"""
Admin Roles API Router

提供用户角色管理的 API 端点：
- GET /api/admin/users - 用户列表（含角色）
- PUT /api/admin/users/{user_id}/role - 修改用户角色

仅 admin 可访问。
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.deps import get_admin_user, get_db, ROLE_HIERARCHY, audit_log
from models import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin-roles"])


class RoleUpdateRequest(BaseModel):
    """角色修改请求"""
    role: str = Field(..., pattern=r'^(viewer|editor|admin)$')


@router.get("/users")
async def list_users(
    db_session: Session = Depends(get_db),
    admin_user: User = Depends(get_admin_user)
):
    """获取所有用户列表（含角色信息）"""
    users = db_session.query(User).order_by(User.created_at.desc()).all()
    return {
        "success": True,
        "users": [u.to_dict() for u in users]
    }


@router.put("/users/{user_id}/role")
async def update_user_role(
    user_id: int,
    request: RoleUpdateRequest,
    db_session: Session = Depends(get_db),
    admin_user: User = Depends(get_admin_user)
):
    """修改指定用户的角色"""
    target_user = db_session.get(User, user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="用户不存在")

    # 禁止修改自己的角色
    if target_user.id == admin_user.id:
        raise HTTPException(status_code=400, detail="不能修改自己的角色")

    if target_user.account_type == 'service' and request.role == 'admin':
        raise HTTPException(status_code=400, detail="服务账户不能设置为管理员")

    # 设置角色，is_admin 由 models.py 的 SQLAlchemy event listener 自动同步
    old_role = target_user.role
    target_user.role = request.role

    # 角色提升属敏感操作，落 SecurityLog 审计
    audit_log(
        user_id=admin_user.id,
        action='admin.user_role.update',
        resource_type='user',
        resource_id=target_user.id,
        details={'username': target_user.username, 'old_role': old_role, 'new_role': request.role},
        db_session=db_session,
    )

    db_session.commit()
    logger.info(f"Admin {admin_user.username} updated user {target_user.username} role: {old_role} -> {request.role}")

    return {
        "success": True,
        "user": target_user.to_dict()
    }
