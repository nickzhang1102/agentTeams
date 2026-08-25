"""
Task Types - Agent 任务自主拆解与编排的类型定义

TypedDict 定义用于：
1. LLM 结构化输出约束
2. 前端 SSE 事件数据格式
3. 任务运行时状态跟踪

参见 feature-design 2026-06-10-agent-step-orchestration 第 2.1 节。
"""
from typing import TypedDict, List, Literal, Optional, NotRequired, Dict


class SubTask(TypedDict):
    """单个子任务

    Attributes:
        id: 子任务ID（如"subtask_1"）
        goal: 子任务目标描述
        tools: 工具链（如["web_search", "grep"]）
        status: 执行状态
        result: 执行结果摘要
        added_dynamically: 是否动态追加
    """
    id: str
    goal: str
    tools: List[str]
    status: Literal["pending", "running", "completed", "failed", "skipped"]
    result: str
    added_dynamically: bool
    raw_tool_results: NotRequired[Dict]
    evidence_map: NotRequired[List[Dict]]


class TaskDecomposition(TypedDict):
    """任务分解计划

    Attributes:
        agent_id: Agent ID
        agent_name: Agent 名称
        original_task: 原始任务描述
        subtasks: 子任务列表
        current_subtask_id: 当前执行的子任务ID
    """
    agent_id: str
    agent_name: str
    original_task: str
    subtasks: List[SubTask]
    current_subtask_id: Optional[str]
    degraded: NotRequired[bool]
    degradation_reason: NotRequired[str]


class DecompositionResult(TypedDict):
    """LLM 结构化分解输出

    LLM call_structured() 返回格式，用于转换为 TaskDecomposition。

    Attributes:
        subtasks: LLM 输出的子任务列表（未完全规范化）
        reasoning: 分解理由
    """
    subtasks: List[dict]
    reasoning: str
    degraded: NotRequired[bool]
    degradation_reason: NotRequired[str]


class AdjustmentDecision(TypedDict):
    """动态调整决策

    检查子任务执行结果后，判断是否需要调整计划。

    Attributes:
        action: 调整动作类型
        reason: 调整原因
        new_subtasks: 新增/修改的子任务（仅 add_subtask / modify_subtask 时有值）
    """
    action: Literal["continue", "add_subtask", "modify_subtask", "skip", "abort"]
    reason: str
    new_subtasks: List[SubTask]


# 常量定义
MAX_SUBTASKS = 10  # 子任务数量上限，防止无限追加

# 工具链模板（按 Agent 类型）
# 规则：knowledge_search 永远不作为唯一工具，必须搭配 web_search
TOOL_CHAIN_TEMPLATES = {
    "medical": ["web_search", "knowledge_search"],  # 医疗类：网络搜索 + 知识库
    "research": ["web_search", "grep", "glob", "knowledge_search"],  # 研究类：搜索 + 检索 + 知识
    "analysis": ["grep", "glob", "knowledge_search"],  # 分析类：代码/文件检索 + 知识
    "default": ["web_search", "knowledge_search"],  # 默认：基础搜索 + 知识
}
