"""
Leader 模块

提供 Leader Agent 协调功能的模块化实现（LangGraph 编排层）
"""

# === LangGraph 编排层 ===
from .workflow_state import LeaderWorkflowState
from .langgraph_workflow import create_leader_workflow_graph
from .sse_streamer import SSEStreamer

# LangGraph 编排层入口
from .langgraph_entry import (
    async_run_leader_workflow,
    async_continue_leader_workflow,
)

# LangGraph 编排层节点
from .workflow_nodes import (
    requirement_loop_node,
    route_after_requirement,
    human_input_node,
    team_form_dag_node,
    initialize_node_services,
    agent_execution_node,
    initialize_executor_services,
    summarize_node,
    initialize_summarize_services
)

# DAG 执行计划生成器
from .dag_planner import DAGPlanner, DAGExecutionPlan, DAGNode, ExecutionBatch

# 批次执行器
from .batch_executor import BatchExecutor
from .execution_result import AgentExecutionResult

# === 任务编排层 ===
from .task_types import (
    SubTask,
    TaskDecomposition,
    DecompositionResult,
    AdjustmentDecision,
    MAX_SUBTASKS,
    TOOL_CHAIN_TEMPLATES,
)
from .task_planner import TaskPlanner
from .subtask_executor import SubTaskExecutor
from .task_runtime import TaskRuntime

__all__ = [
    # === LangGraph 编排层 ===
    'LeaderWorkflowState',
    'create_leader_workflow_graph',
    'SSEStreamer',
    # LangGraph 入口
    'async_run_leader_workflow',
    'async_continue_leader_workflow',
    # LangGraph 节点
    'requirement_loop_node',
    'route_after_requirement',
    'human_input_node',
    'team_form_dag_node',
    'initialize_node_services',
    'agent_execution_node',
    'initialize_executor_services',
    'summarize_node',
    'initialize_summarize_services',
    # DAG 执行计划生成器
    'DAGPlanner',
    'DAGExecutionPlan',
    'DAGNode',
    'ExecutionBatch',
    # 批次执行器
    'BatchExecutor',
    'AgentExecutionResult',
    # === 任务编排层 ===
    'SubTask',
    'TaskDecomposition',
    'DecompositionResult',
    'AdjustmentDecision',
    'MAX_SUBTASKS',
    'TOOL_CHAIN_TEMPLATES',
    'TaskPlanner',
    'SubTaskExecutor',
    'TaskRuntime',
]
