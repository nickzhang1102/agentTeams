"""Admin Pydantic 请求模型

提供 admin 路由模块使用的请求体模型定义。
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class AgentCreateRequest(BaseModel):
    """创建 Agent 请求"""
    agent_id: str = Field(..., min_length=1, description="Agent 标识")
    name: str = Field(..., min_length=1, description="Agent 名称")
    description: Optional[str] = Field(default="", description="Agent 描述")
    model: Optional[str] = Field(default="inherit", description="使用的模型")
    content: Optional[str] = Field(default="", description="Markdown 内容")
    # 新增字段
    role: Optional[str] = Field(default=None, max_length=200, description="角色一句话描述")
    persona: Optional[str] = Field(default=None, description="人设描述")
    expertise: Optional[str] = Field(default=None, description="核心专长")
    approach: Optional[str] = Field(default=None, description="工作方式")
    capabilities: Optional[List[str]] = Field(default=[], description="能力标签")
    skill_level: int = Field(default=3, ge=1, le=5, description="专业度 1-5")
    tags: Optional[List[str]] = Field(default=[], description="业务域标签")
    preferred_contexts: Optional[List[str]] = Field(default=[], description="适用场景")
    portrait_url: Optional[str] = Field(default=None, max_length=500, description="头像 URL（仅允许 http/https）")

    @field_validator('portrait_url')
    @classmethod
    def validate_portrait_url(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v != '':
            if not v.startswith(('http://', 'https://')):
                raise ValueError('portrait_url 必须以 http:// 或 https:// 开头')
        return v


class AgentUpdateRequest(BaseModel):
    """更新 Agent 请求"""
    name: Optional[str] = Field(default=None, description="Agent 名称")
    description: Optional[str] = Field(default=None, description="Agent 描述")
    model: Optional[str] = Field(default=None, description="使用的模型")
    content: Optional[str] = Field(default=None, description="Markdown 内容")
    # 新增字段
    role: Optional[str] = Field(default=None, max_length=200)
    persona: Optional[str] = Field(default=None)
    expertise: Optional[str] = Field(default=None)
    approach: Optional[str] = Field(default=None)
    capabilities: Optional[List[str]] = Field(default=None)
    skill_level: Optional[int] = Field(default=None, ge=1, le=5)
    tags: Optional[List[str]] = Field(default=None)
    preferred_contexts: Optional[List[str]] = Field(default=None)
    portrait_url: Optional[str] = Field(default=None, max_length=500)

    @field_validator('portrait_url')
    @classmethod
    def validate_portrait_url(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v != '':
            if not v.startswith(('http://', 'https://')):
                raise ValueError('portrait_url 必须以 http:// 或 https:// 开头')
        return v


class AgentGenerateRequest(BaseModel):
    """AI 生成 Agent 配置请求"""
    name: str = Field(..., min_length=1, description="Agent 名称")
    description: Optional[str] = Field(default="", description="Agent 描述（可选）")
    agent_type: Optional[str] = Field(default="", description="Agent 类型：medical/business/technical/other")


class SettingUpdateRequest(BaseModel):
    """更新系统设置请求"""
    value: str = Field(..., description="配置值")


class OpenHarnessConfigUpdateRequest(BaseModel):
    """批量更新 OpenHarness 配置请求"""
    configs: Dict[str, Any] = Field(..., description="配置键值对")


class AgentMcpPermissionsUpdateRequest(BaseModel):
    """更新 Agent MCP 权限请求"""
    permissions: List[Dict[str, Any]] = Field(default=[], description="权限列表")


class PriorityRuleCreateRequest(BaseModel):
    """创建优先级规则请求"""
    trigger_scene: Optional[str] = Field(default=None, description="触发场景")
    trigger_risk_level: Optional[str] = Field(default=None, description="触发风险等级")
    trigger_category: Optional[str] = Field(default=None, description="触发分类")
    agent_id: str = Field(..., min_length=1, description="目标 Agent ID")
    priority: int = Field(..., ge=0, le=100, description="优先级值")
    rule_priority: Optional[int] = Field(default=0, description="规则优先级")
    description: Optional[str] = Field(default=None, description="规则描述")
    is_active: Optional[bool] = Field(default=True, description="启用状态")


class PriorityRuleUpdateRequest(BaseModel):
    """更新优先级规则请求"""
    trigger_scene: Optional[str] = Field(default=None, description="触发场景")
    trigger_risk_level: Optional[str] = Field(default=None, description="触发风险等级")
    trigger_category: Optional[str] = Field(default=None, description="触发分类")
    agent_id: Optional[str] = Field(default=None, description="目标 Agent ID")
    priority: Optional[int] = Field(default=None, ge=0, le=100, description="优先级值")
    rule_priority: Optional[int] = Field(default=None, description="规则优先级")
    description: Optional[str] = Field(default=None, description="规则描述")
    is_active: Optional[bool] = Field(default=None, description="启用状态")


class FeaturedConversationUpdateRequest(BaseModel):
    """更新精选案例请求"""
    conversation_id: int = Field(..., description="对话 ID")
    is_featured: bool = Field(..., description="是否精选")
    featured_order: Optional[int] = Field(default=0, ge=0, description="排序序号")
