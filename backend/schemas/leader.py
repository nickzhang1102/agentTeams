"""Leader 结构化输出模型。"""
import re
from typing import Literal, List, Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator


# 各场景通过阈值（与 route_after_requirement 保持一致）
_SCENE_THRESHOLDS = {
    'technology': 60, 'medical': 50, 'investment': 60,
    'legal': 55, 'social_hotspot': 45, 'decision_making': 55, 'general': 50,
}

_CATEGORY_ALIASES = {
    "tech": "technology",
    "technical": "technology",
    "dev": "technology",
    "software": "technology",
    "技术": "technology",
    "技术开发": "technology",
    "科技": "technology",
    "编程": "technology",
    "软件开发": "technology",
    "business": "business",
    "commercial": "business",
    "strategy": "business",
    "商业": "business",
    "商业咨询": "business",
    "商业化": "business",
    "市场": "business",
    "营销": "business",
    "管理": "business",
    "medical": "medical",
    "health": "medical",
    "healthcare": "medical",
    "medicine": "medical",
    "医疗": "medical",
    "医疗健康": "medical",
    "健康": "medical",
    "医学": "medical",
    "investment": "investment",
    "finance": "investment",
    "financial": "investment",
    "securities": "investment",
    "投资": "investment",
    "投资理财": "investment",
    "理财": "investment",
    "金融": "investment",
    "证券": "investment",
    "science": "science",
    "research": "science",
    "科研": "science",
    "科学": "science",
    "学术": "science",
    "writing": "writing",
    "content": "writing",
    "写作": "writing",
    "创作": "writing",
    "文案": "writing",
    "legal": "legal",
    "law": "legal",
    "法律": "legal",
    "合规": "legal",
    "合同": "legal",
    "education": "education",
    "learning": "education",
    "教学": "education",
    "教育": "education",
    "学习": "education",
    "lifestyle": "lifestyle",
    "life": "lifestyle",
    "生活": "lifestyle",
    "生活服务": "lifestyle",
    "其他": "other",
    "其它": "other",
    "通用": "other",
    "无法归类": "other",
}


def normalize_category_key(category: Any) -> str:
    """Normalize model-produced category labels to the frontend category keys."""
    if category is None:
        return "other"

    key = str(category).strip()
    if not key:
        return "other"

    key = key.lower().replace("-", "_").replace(" ", "_")
    valid_categories = {
        "technology", "business", "medical", "investment", "science",
        "writing", "legal", "education", "lifestyle", "other",
    }
    if key in valid_categories:
        return key

    return _CATEGORY_ALIASES.get(key, "other")


def _coerce_text_list(value: Any) -> list[str]:
    """Normalize model-produced bullet text into a list of strings."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if item is not None and str(item).strip()]
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []

        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if len(lines) > 1:
            items = [
                re.sub(r"^\s*(?:[-*+]|\d+[.)、]|[（(]?\d+[）)])\s*", "", line).strip()
                for line in lines
            ]
            return [item for item in items if item]

        numbered_parts = re.split(r"\s+(?=\d+[.)、]\s*)", text)
        if len(numbered_parts) > 1:
            return [
                re.sub(r"^\d+[.)、]\s*", "", part).strip()
                for part in numbered_parts
                if re.sub(r"^\d+[.)、]\s*", "", part).strip()
            ]

        return [text]
    return [str(value).strip()] if str(value).strip() else []


class QuestionOption(BaseModel):
    """需求追问及预设选项。"""

    question: str
    options: list[str] = Field(min_length=3, description="至少3个与问题场景匹配的具体预设选项")
    selection_type: Literal["single", "multiple"] = "single"


class AssessmentResult(BaseModel):
    """需求评估结构化结果。"""

    model_config = ConfigDict(populate_by_name=True)

    score: int = Field(validation_alias=AliasChoices("score", "total_score"))
    passed: bool = False
    risk_level: Literal["low", "medium", "high"]
    scene: Literal[
        "technology",
        "medical",
        "investment",
        "legal",
        "social_hotspot",
        "decision_making",
        "general",
    ]
    category: Literal[
        "technology",
        "business",
        "medical",
        "investment",
        "science",
        "writing",
        "legal",
        "education",
        "lifestyle",
        "other",
    ] = "other"
    questions: list[QuestionOption] = Field(default_factory=list)
    details: str = Field(default="", validation_alias=AliasChoices("details", "analysis"))
    scores: dict[str, int] = Field(default_factory=dict)
    risk_reason: str = ""

    @field_validator("category", mode="before")
    @classmethod
    def normalize_category(cls, value: Any) -> str:
        return normalize_category_key(value)

    @model_validator(mode="after")
    def compute_passed(self) -> "AssessmentResult":
        """基于 score 和 scene 计算 passed，不信任 LLM 返回的 passed。"""
        threshold = _SCENE_THRESHOLDS.get(self.scene, 50)
        object.__setattr__(self, "passed", self.score >= threshold)
        return self


class AgentSelection(BaseModel):
    """团队选择中的单个 Agent。"""

    agent_id: str
    agent_name: str
    role_description: str
    reason: str = ""
    tools: list[str] = Field(default_factory=list)


class TeamSelectionResult(BaseModel):
    """团队选择结构化结果。"""

    model_config = ConfigDict(populate_by_name=True)

    agents: list[AgentSelection] = Field(validation_alias=AliasChoices("agents", "selected_agents"))
    reasoning: str = Field(validation_alias=AliasChoices("reasoning", "analysis"))
    team_strategy: str = ""


class ClaimEvidenceReference(BaseModel):
    """One model-proposed evidence relation; the server validates the ID."""

    evidence_id: str
    relation: Literal["supports", "contradicts", "qualifies"] = "supports"


class ReportClaim(BaseModel):
    """A report assertion before server-side support-status validation."""

    claim_id: str = "claim"
    text: str
    claim_type: Literal[
        "fact",
        "interpretation",
        "recommendation",
        "risk",
        "uncertainty",
    ]
    confidence: float | None = Field(default=None, ge=0, le=1)
    evidence_relations: list[ClaimEvidenceReference] = Field(default_factory=list)
    agent_refs: list[str] = Field(default_factory=list)


class FinalReportResult(BaseModel):
    """最终汇总结构化结果。"""

    title: str
    executive_summary: str
    key_findings: list[str]
    recommendations: list[str]
    risks: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    agent_summaries_used: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    claims: list[ReportClaim] = Field(
        default_factory=list,
        description=(
            "关键事实、解释、建议、风险和不确定性。每条只引用输入中显式提供的 evidence_id；"
            "没有证据时保留空 evidence_relations，不得虚构引用或 support status。"
        ),
    )
    visual_blocks: list["ReportVisualBlock"] = Field(default_factory=list)
    markdown_report: str = Field(
        description=(
            "完整 Markdown 最终报告正文，不是摘要字段的复述。必须直接回应用户需求，"
            "整合各 Agent 的关键发现、判断依据、执行路径和风险边界；"
            "正文长度应随问题复杂度、Agent 数量和证据量自适应，避免重复扩写或只给摘要。"
        )
    )

    @field_validator(
        "key_findings",
        "recommendations",
        "risks",
        "next_steps",
        "agent_summaries_used",
        "evidence_refs",
        mode="before",
    )
    @classmethod
    def normalize_text_list_fields(cls, value: Any) -> list[str]:
        return _coerce_text_list(value)

    def summary_payload(self) -> dict:
        """返回前端摘要区需要的最小 payload。"""
        return {
            "title": self.title,
            "executive_summary": self.executive_summary,
            "key_findings": self.key_findings,
            "recommendations": self.recommendations,
            "risks": self.risks,
            "next_steps": self.next_steps,
        }

    def structured_payload(self) -> dict:
        """返回可持久化的完整结构化最终报告。"""
        return self.model_dump()


class AgentReportSummary(BaseModel):
    """Agent 报告摘要。"""

    one_sentence: str
    key_findings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.6, ge=0, le=1)
    evidence_refs: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)

    @field_validator(
        "key_findings",
        "recommendations",
        "risks",
        "evidence_refs",
        "open_questions",
        mode="before",
    )
    @classmethod
    def normalize_text_list_fields(cls, value: Any) -> list[str]:
        return _coerce_text_list(value)


class ReportVisualBlock(BaseModel):
    """报告图表块协议占位，渲染在后续 roadmap item 实现。"""

    block_id: str
    type: Literal[
        "risk_matrix",
        "decision_matrix",
        "agent_opinion_compare",
        "timeline",
        "priority_table",
    ]
    title: str
    data: dict[str, Any]
    evidence_refs: list[str] = Field(default_factory=list)


class ReportEvidence(BaseModel):
    """报告证据引用。"""

    schema_version: int = 1
    evidence_id: str
    source_type: Literal[
        "tool_result",
        "subtask_result",
        "agent_report",
        "web",
        "knowledge",
        "memory",
        "user_input",
    ]
    source_id: str | None = None
    title: str
    excerpt: str
    raw_ref: str | None = None
    url: str | None = None
    provider: str | None = None
    locator: dict[str, Any] = Field(default_factory=dict)
    rank: int | None = None
    relevance_score: float | None = None
    content_hash: str | None = None
    source_version: str | None = None
    completeness: Literal["passage", "snippet", "legacy", "unavailable"] = "legacy"
    agent_id: str | None = None
    subtask_id: str | None = None
    created_at: str


class StructuredAgentReport(BaseModel):
    """Agent 结构化报告。"""

    summary: AgentReportSummary
    markdown_report: str
    visual_blocks: list[ReportVisualBlock] = Field(default_factory=list)
    claims: list[ReportClaim] = Field(default_factory=list)


class StructuredAgentResult(BaseModel):
    """Agent 结构化结果。"""

    conclusion: str
    evidence: list[str]
    risks: list[str] = Field(default_factory=list)
    confidence: float
    sources: list[str] = Field(default_factory=list)


# === 任务编排结构化输出（2026-06-10-agent-step-orchestration）===

class StructuredSubTask(BaseModel):
    """LLM 输出的子任务结构"""

    id: str = Field(description="子任务ID，格式如 subtask_1")
    goal: str = Field(description="子任务目标描述")
    tools: List[str] = Field(default_factory=list, description="工具链，如 ['web_search', 'file_read']")
    reasoning: str = Field(default="", description="为什么需要这个子任务")


class TaskDecompositionOutput(BaseModel):
    """LLM 任务分解结构化输出"""

    subtasks: List[StructuredSubTask] = Field(description="分解后的子任务列表")
    reasoning: str = Field(description="整体分解理由")


class AdjustmentDecisionOutput(BaseModel):
    """LLM 动态调整决策结构化输出"""

    action: Literal["continue", "add_subtask", "modify_subtask", "skip", "abort"] = Field(
        description="调整动作类型"
    )
    reason: str = Field(description="调整原因")
    new_subtasks: List[StructuredSubTask] = Field(
        default_factory=list,
        description="新增/修改的子任务（仅 add_subtask / modify_subtask 时提供）"
    )
