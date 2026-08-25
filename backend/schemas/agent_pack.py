"""
Agent Pack Pydantic schemas
"""
from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, Field


class PackAgentItem(BaseModel):
    agent_id: str = Field(..., min_length=1)
    role: str = ""
    order: int = Field(default=1, ge=1)


class AgentPackCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    category: str = Field(default="custom")
    agents: List[PackAgentItem] = Field(..., min_length=1, max_length=10)
    tags: List[str] = Field(default_factory=list)


class AgentPackUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    description: Optional[str] = None
    category: Optional[str] = None
    agents: Optional[List[PackAgentItem]] = None
    tags: Optional[List[str]] = None


class AgentPackResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    category: str
    is_system: bool
    creator_id: Optional[int]
    agents: List[dict]
    tags: List[str]
    usage_count: int
    created_at: Optional[str]
    updated_at: Optional[str]
