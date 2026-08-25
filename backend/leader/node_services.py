"""
Node Services

服务依赖容器与初始化函数。从 workflow_nodes.py 提取
（2026-06-18 workflow-nodes-split refactor）。

使用 contextvars.ContextVar 存储服务依赖，避免模块级全局变量在并发会话中互相覆盖。
"""
import logging
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Optional, Any

logger = logging.getLogger(__name__)


@dataclass
class NodeServices:
    """节点函数共享的服务依赖容器"""
    llm_service: Any = None
    max_tokens_limit: int = 16384
    agent_reader: Any = None
    db_session: Any = None
    harness_coordinator: Any = None
    max_parallel: int = 5
    llm_api_key: Optional[str] = None
    llm_base_url: Optional[str] = None
    llm_default_model: str = "ep-default"
    knowledge_retriever: Any = None
    tool_registry: Any = None  # 工具注册表（BatchExecutor 任务编排用）


# ContextVar：并发安全，每个请求/协程独立
_current_services: ContextVar[Optional[NodeServices]] = ContextVar('_current_services', default=None)


def get_services() -> NodeServices:
    """获取当前上下文的 NodeServices 实例

    Returns:
        NodeServices 实例

    Raises:
        RuntimeError: 如果未初始化（应在入口函数中调用 set_services）
    """
    svc = _current_services.get()
    if svc is None:
        logger.warning("NodeServices not initialized in context, returning default empty instance")
        return NodeServices()
    return svc


def set_services(services: NodeServices) -> None:
    """设置当前上下文的 NodeServices 实例"""
    _current_services.set(services)


def should_stop_workflow(state) -> bool:
    """检查工作流是否收到停止请求（内存标志优先，再查持久化取消信号）

    供需求评估 / 团队组建 / 汇总等各阶段节点入口调用：用户点停止后，
    这些阶段也能及时退出，避免继续消耗 token（尤其在汇总阶段跳过 LLM 报告生成）。
    与 execution_nodes._check_stop_flag 共享同一判定，语义一致。
    """
    # 内存标志同样用 `is True` 严格判断，避免被其它 truthy 值误判为已停止
    if state.get("stop_requested") is True:
        return True
    session_id = state.get("session_id")
    if not session_id:
        return False
    svc = get_services()
    db = svc.db_session
    if db is None:
        return False
    try:
        from .leader_persistence import is_session_stop_requested
        return is_session_stop_requested(db, session_id)
    except Exception:
        logger.exception("should_stop_workflow: DB 检查失败，按未停止处理")
        return False


def stop_workflow(state, *, reason: str = "user_requested") -> dict:
    """Converge persistent state and build the single stopped SSE event."""
    from .leader_events import make_execution_stopped_event
    from .leader_persistence import mark_session_stopped

    session_id = state.get("session_id")
    svc = get_services()
    if svc.db_session is not None and session_id:
        mark_session_stopped(svc.db_session, session_id, reason=reason)
    return make_execution_stopped_event(
        session_id,
        state.get("locale", "zh-CN"),
    )


# ==================== 向后兼容的初始化函数 ====================
# 保留旧 API 签名，内部改为创建 NodeServices 并设置到 contextvar。
# 调用方（langgraph_entry.py）无需大改即可过渡。

def initialize_node_services(
    llm_service: Any,
    max_tokens_limit: int = 16384,
    agent_reader: Any = None,
    db_session: Any = None
) -> None:
    """初始化节点所需的服务（兼容旧接口，内部委托 NodeServices）"""
    svc = _current_services.get()
    if svc is None:
        svc = NodeServices()
        _current_services.set(svc)
    svc.llm_service = llm_service
    svc.max_tokens_limit = max_tokens_limit
    svc.agent_reader = agent_reader
    svc.db_session = db_session
    logger.info("Node services initialized")


def initialize_executor_services(
    harness_coordinator: Any,
    max_parallel: int = 5,
    knowledge_retriever: Any = None
) -> None:
    """初始化 Agent 执行节点所需的服务（兼容旧接口）"""
    svc = _current_services.get()
    if svc is None:
        svc = NodeServices()
        _current_services.set(svc)
    svc.harness_coordinator = harness_coordinator
    svc.max_parallel = max_parallel
    svc.knowledge_retriever = knowledge_retriever
    logger.info("Executor services initialized")


def initialize_summarize_services(
    db_session: Any
) -> None:
    """初始化结果汇总节点所需的服务（兼容旧接口）"""
    svc = _current_services.get()
    if svc is None:
        svc = NodeServices()
        _current_services.set(svc)
    svc.db_session = db_session
    logger.info("Summarize services initialized")
