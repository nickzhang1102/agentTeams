"""
Workflow Template Pydantic schemas
"""
from typing import Optional, List

from pydantic import BaseModel, Field


class TemplateAgentItem(BaseModel):
    agent_id: str = Field(..., min_length=1)
    role: str = ""
    order: int = Field(default=1, ge=1)


class WorkflowTemplateCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    category: str = Field(default="custom")
    pack_id: Optional[int] = None
    agents: Optional[List[TemplateAgentItem]] = Field(default=None, max_length=10)
    skip_assessment: bool = False
    assessment_threshold: int = Field(default=60, ge=0, le=100)
    system_prompt_addition: Optional[str] = Field(default=None, max_length=2000)


class WorkflowTemplateUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    description: Optional[str] = None
    category: Optional[str] = None
    pack_id: Optional[int] = None
    agents: Optional[List[TemplateAgentItem]] = None
    skip_assessment: Optional[bool] = None
    assessment_threshold: Optional[int] = Field(default=None, ge=0, le=100)
    system_prompt_addition: Optional[str] = Field(default=None, max_length=2000)


class ApplyTemplateRequest(BaseModel):
    conversation_id: int = Field(..., gt=0)
    message: str = Field(..., min_length=1)
    file_ids: Optional[List[int]] = Field(default_factory=list)
    locale: Optional[str] = None
