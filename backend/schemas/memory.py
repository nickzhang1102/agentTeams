"""记忆提取结构化输出模型。"""
from typing import Literal

from pydantic import BaseModel, Field


class ExtractedMemory(BaseModel):
    """从对话中提取的单条记忆。"""

    content: str = Field(description="记忆内容，一句话摘要")
    memory_type: Literal["preference", "decision", "fact", "constraint"] = Field(
        description="记忆类型：用户偏好 / 决策结论 / 事实信息 / 约束条件"
    )
    importance: float = Field(
        default=0.5, ge=0.0, le=1.0,
        description="重要性评分 0.0-1.0"
    )
    tags: list[str] = Field(default_factory=list, description="标签列表")


class MemoryExtractionResult(BaseModel):
    """对话记忆提取结构化结果。"""

    memories: list[ExtractedMemory] = Field(
        default_factory=list,
        description="从对话中提取的记忆列表，无值得提取的内容时为空列表"
    )
