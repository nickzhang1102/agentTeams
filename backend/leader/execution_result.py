"""
Agent Execution Result Types

定义 Agent 执行结果的规范化结构（TypedDict）
"""
from typing import TypedDict, List, Dict, Optional, Any, NotRequired


class AgentExecutionResult(TypedDict):
    """单个 Agent 执行结果（规范化结构）

    用于统一 HarnessCoordinator.execute_agent() 返回结果格式，
    并记录批次执行元数据。

    Fields:
        agent_id: Agent 标识符
        agent_name: Agent 显示名称
        success: 执行是否成功
        status: 执行状态（"completed" | "failed" | "stopped"）
        content: Agent 输出内容
        summary: Agent 报告摘要
        structured_report: Agent 结构化报告
        raw_tool_results: 原始工具结果
        evidence_map: 证据引用映射
        tool_calls: 工具调用记录列表
        tokens_used: Token 消耗量
        execution_time: 执行耗时（秒）
        error: 错误信息（失败时）
        batch_index: 所属批次索引
        created_at: 创建时间（ISO 格式）
    """
    agent_id: str
    agent_name: str
    success: bool
    status: str                    # "completed" | "failed" | "stopped"
    content: str
    content_locale: NotRequired[str]
    summary: NotRequired[Optional[Dict[str, Any]]]
    structured_report: NotRequired[Optional[Dict[str, Any]]]
    raw_tool_results: NotRequired[Optional[Dict[str, Any]]]
    evidence_map: NotRequired[Optional[List[Dict[str, Any]]]]
    tool_calls: List[Dict]         # [{"tool", "input", "output"}]
    tokens_used: int
    execution_time: float
    error: Optional[str]
    batch_index: int               # 所属批次索引
    created_at: str                # ISO 时间戳
    decomposition: Optional[Dict[str, Any]]
    progress_summary: Optional[Dict[str, Any]]
    quality_status: NotRequired[str]
    degradation_reason: NotRequired[Optional[str]]
