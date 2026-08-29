"""
LangGraph Workflow Definition

创建 Leader 状态图（StateGraph），定义节点 + 边 + 条件分支
本 feature 使用 mock 节点验证骨架，后续 feature 替换为真实节点
"""
import logging
from typing import Dict
from langgraph.graph import StateGraph, END

from .workflow_state import LeaderWorkflowState
from .workflow_nodes import (
    requirement_loop_node,
    route_after_requirement,
    route_after_human_input,
    human_input_node,
    team_form_dag_node,
    agent_execution_node,
    summarize_node
)

logger = logging.getLogger(__name__)


def route_after_agent_execution(state: LeaderWorkflowState) -> str:
    """Route stopped executions directly to END instead of summarize."""
    if state.get("current_phase") == "execution_stopped":
        return "end"
    return "summarize"


def route_after_team_form(state: LeaderWorkflowState) -> str:
    """Skip Agent execution when team formation observed cancellation."""
    if state.get("current_phase") == "execution_stopped":
        return "end"
    return "agent_execution"


def create_leader_workflow_graph():
    """创建 Leader 状态图（审核已移除，Agent 执行完成后直接汇总）

    Returns:
        Compiled StateGraph，可调用 invoke() / astream_events(version="v2")
    """
    graph = StateGraph(LeaderWorkflowState)

    # 添加需求循环节点
    graph.add_node("requirement_loop", requirement_loop_node)
    graph.add_node("human_input", human_input_node)

    # 添加团队组建 + DAG 生成节点
    graph.add_node("team_form_dag", team_form_dag_node)

    # 添加 Agent 执行节点
    graph.add_node("agent_execution", agent_execution_node)

    # 添加结果汇总节点
    graph.add_node("summarize", summarize_node)

    # 设置入口：requirement_loop
    graph.set_entry_point("requirement_loop")

    # 需求评估后条件路由
    graph.add_conditional_edges(
        "requirement_loop",
        route_after_requirement,
        {
            "team_form": "team_form_dag",
            "human_input": "human_input",
            "end": END
        }
    )

    # human_input：正常提问 → END 等待用户回答（由 continue_leader_workflow 恢复）；
    # 问题无效的降级路径 → 直接进入团队组建（详见 route_after_human_input）
    graph.add_conditional_edges(
        "human_input",
        route_after_human_input,
        {
            "team_form": "team_form_dag",
            "end": END
        }
    )

    # team_form_dag → agent_execution；停止时直接结束
    graph.add_conditional_edges(
        "team_form_dag",
        route_after_team_form,
        {
            "agent_execution": "agent_execution",
            "end": END,
        },
    )

    # agent_execution → summarize；用户停止时直接结束，避免生成 completed 报告
    graph.add_conditional_edges(
        "agent_execution",
        route_after_agent_execution,
        {
            "summarize": "summarize",
            "end": END,
        }
    )

    # summarize → END
    graph.add_edge("summarize", END)

    logger.info("Leader workflow graph created (review removed)")
    return graph.compile()
