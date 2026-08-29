"""
FastAPI Skills API 路由模块

实现技能管理 API：
- GET / - 获取所有技能列表
- GET /{skill_id} - 获取单个技能详情
- POST /activate - 激活技能
- POST /deactivate - 停用技能
- GET /active - 获取当前激活的技能
- POST /reset - 重置所有激活的技能
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.deps import get_current_user, get_admin_user
from services.skills_manager import get_skills_manager

logger = logging.getLogger(__name__)

# 创建 Skills 路由
router = APIRouter(prefix="/api/skills", tags=["skills"])


class SkillsListResponse(BaseModel):
    success: bool
    skills: list


class SkillDetailResponse(BaseModel):
    success: bool
    skill: Optional[dict] = None


class ActivateRequest(BaseModel):
    skill_id: str = Field(..., min_length=1)


class ActivateResponse(BaseModel):
    success: bool
    active_skills: list
    active_tools: list


class ActiveSkillsResponse(BaseModel):
    success: bool
    active_skills: list
    active_tools: list
    system_prompt_enhancement: str


class ResetResponse(BaseModel):
    success: bool
    active_skills: list
    active_tools: list


@router.get("", response_model=SkillsListResponse)
async def get_skills(
    user = Depends(get_current_user)
):
    """获取所有可用的技能列表"""
    try:
        manager = get_skills_manager()
        skills = manager.list_skills()

        # 添加激活状态
        for skill in skills:
            skill['active'] = skill['id'] in manager.active_skills

        return {
            "success": True,
            "skills": skills
        }
    except Exception as e:
        logger.error(f"Get skills failed: {e}", exc_info=True)
        return {
            "success": False,
            "skills": []
        }


# 注意：/active 必须注册在 /{skill_id} 之前，否则会被路径参数路由吞掉
# （Starlette 按注册顺序匹配，"active" 会被当作 skill_id 查询后返回 404 语义）。

@router.get("/active", response_model=ActiveSkillsResponse)
async def get_active_skills(
    user = Depends(get_current_user)
):
    """获取当前激活的技能"""
    try:
        manager = get_skills_manager()

        return {
            "success": True,
            "active_skills": [s.to_dict() for s in manager.get_active_skills()],
            "active_tools": manager.get_active_tools(),
            "system_prompt_enhancement": manager.build_system_prompt_enhancement()
        }
    except Exception as e:
        logger.error(f"Get active skills failed: {e}", exc_info=True)
        return {
            "success": False,
            "active_skills": [],
            "active_tools": [],
            "system_prompt_enhancement": ""
        }


@router.get("/{skill_id}", response_model=SkillDetailResponse)
async def get_skill(
    skill_id: str,
    user = Depends(get_current_user)
):
    """获取单个技能的详细信息"""
    try:
        manager = get_skills_manager()
        skill = manager.get_skill(skill_id)

        if not skill:
            return {
                "success": False,
                "skill": None
            }

        skill_dict = skill.to_dict()
        skill_dict['active'] = skill_id in manager.active_skills

        return {
            "success": True,
            "skill": skill_dict
        }
    except Exception as e:
        logger.error(f"Get skill failed: {e}", exc_info=True)
        return {
            "success": False,
            "skill": None
        }


@router.post("/activate", response_model=ActivateResponse)
async def activate_skill(
    request: ActivateRequest,
    admin = Depends(get_admin_user)
):
    """激活技能（操作全局单例状态，仅管理员）"""
    try:
        manager = get_skills_manager()

        if not manager.activate_skill(request.skill_id):
            raise HTTPException(
                status_code=404,
                detail={
                    "success": False,
                    "error": f"Skill not found: {request.skill_id}"
                }
            )

        return {
            "success": True,
            "active_skills": manager.active_skills,
            "active_tools": manager.get_active_tools()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Activate skill failed: {e}", exc_info=True)
        return {
            "success": False,
            "active_skills": [],
            "active_tools": []
        }


@router.post("/deactivate", response_model=ActivateResponse)
async def deactivate_skill(
    request: ActivateRequest,
    admin = Depends(get_admin_user)
):
    """停用技能（操作全局单例状态，仅管理员）"""
    try:
        manager = get_skills_manager()
        manager.deactivate_skill(request.skill_id)

        return {
            "success": True,
            "active_skills": manager.active_skills,
            "active_tools": manager.get_active_tools()
        }
    except Exception as e:
        logger.error(f"Deactivate skill failed: {e}", exc_info=True)
        return {
            "success": False,
            "active_skills": [],
            "active_tools": []
        }


@router.post("/reset", response_model=ResetResponse)
async def reset_active_skills(
    admin = Depends(get_admin_user)
):
    """重置所有激活的技能（操作全局单例状态，仅管理员）"""
    try:
        manager = get_skills_manager()
        manager.active_skills = []

        return {
            "success": True,
            "active_skills": [],
            "active_tools": []
        }
    except Exception as e:
        logger.error(f"Reset skills failed: {e}", exc_info=True)
        return {
            "success": False,
            "active_skills": [],
            "active_tools": []
        }