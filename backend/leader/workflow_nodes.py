"""
LangGraph Workflow Nodes

聚合 re-export 模块。实际定义分布在：
- node_services.py      — 服务容器与初始化
- leader_events.py      — SSE 事件推送与工厂
- leader_persistence.py — 持久化函数
- requirement_nodes.py  — 需求评估节点
- team_form_nodes.py    — 团队组建节点
- execution_nodes.py    — Agent 执行节点
- summarize_nodes.py    — 结果汇总节点
"""

# ==================== 服务容器 ====================
from .node_services import (  # noqa: F401
    NodeServices,
    get_services,
    set_services,
    initialize_node_services,
    initialize_executor_services,
    initialize_summarize_services,
)

# ==================== SSE 事件 ====================
from .leader_events import _emit  # noqa: F401

# ==================== 持久化函数 ====================
from .leader_persistence import (  # noqa: F401
    _persist_agent_results,
    _save_leader_message,
    _persist_final_report,
    _get_message_seq_cache,
    _get_next_msg_sequence,
    clear_message_seq_cache,
    _message_seq_cache_var,
)

# ==================== 需求评估节点 ====================
from .requirement_nodes import (  # noqa: F401
    requirement_loop_node,
    route_after_requirement,
    route_after_human_input,
    human_input_node,
    _simple_assessment_fallback,
    SCENE_NAMES,
    RISK_LEVEL_MAP,
    SCORE_DIM_NAMES,
    SCENE_THRESHOLDS,
)

# ==================== 团队组建节点 ====================
from .team_form_nodes import (  # noqa: F401
    team_form_dag_node,
    _fallback_team_selection,
    _simple_dag_plan,
    _describe_execution_order,
)

# ==================== Agent 执行节点 ====================
from .execution_nodes import (  # noqa: F401
    agent_execution_node,
    _check_stop_flag,
)

# ==================== 结果汇总节点 ====================
from .summarize_nodes import (  # noqa: F401
    summarize_node,
    _build_agent_summary_input,
    _build_summary_prompt,
    _call_llm_for_summary,
    _fallback_summary,
)
