"""
LangGraph Workflow State Definition

定义 LeaderWorkflowState TypedDict 作为状态图共享状态
"""
from typing import TypedDict, List, Dict, Optional


class LeaderWorkflowState(TypedDict):
    """LangGraph 状态图共享状态

    设计要点：
    - conversation_id / session_id：会话元数据
    - requirement_*：需求完善循环状态
    - team_*：团队组建状态
    - agent_*：Agent 执行状态（Annotated[List, add_messages] 支持追加）
    - sse_events：待发送 SSE 事件队列（追加模式）
    """

    # === 会话元数据 ===
    conversation_id: int
    session_id: Optional[int]          # DB LeaderSession.id
    user_id: Optional[int]             # 用户 ID（用于记忆检索）
    locale: str                        # LeaderSession 生成语言快照
    user_message: str
    history: List[Dict]                # [{"role": "user/assistant", "content": "..."}]
    shared_evidence: List[str]         # 共享证据（文件内容、搜索结果等，由 ContextBuilder 注入）

    # === 需求完善循环 ===
    requirement_loop_count: int        # 当前轮次 (0-3)
    requirement_passed: bool           # 评估是否通过
    requirement_questions: List[str]   # 评估器生成的问题（本轮新问题）
    all_asked_questions: List[Dict]    # 所有已问过的问题（累积，用于去重）
    qa_history: List[Dict]             # 历史 Q&A 配对（累积，用于评估上下文）
    user_answers: List[str]            # 当轮用户回答
    assessment_result: Dict            # {"score", "risk_level", "category", "scene", "details"}

    # === 团队组建 ===
    selected_agents: List[Dict]        # [{"agent_id", "agent_name", "role_description"}]
    dag_execution_plan: Dict           # {"nodes": [...], "edges": [...], "conditions": [...]}

    # === Agent 执行 ===
    agent_results: List[Dict]           # Agent 执行结果列表
    current_agent_index: int           # 当前执行到哪个 Agent
    agent_retry_counts: Dict[str, int] # {"agent_id": retry_count}
    total_tokens: int                  # 总 token 消耗（由 agent_execution_node 计算）

    # === 汇总 ===
    final_report: str

    # === 流程控制 ===
    stop_requested: bool
    current_phase: str
    skip_to_execution: bool            # 跳过需求评估和团队组建
    pre_selected_agents: List[str]     # 用户指定的 agent_id 列表（快速模式）
    assessment_threshold: int          # 评估通过阈值（默认 60）
    system_prompt_addition: Optional[str]  # 注入到 Agent 的额外系统提示

    # === SSE 事件队列 ===
    sse_events: List[Dict]  # SSE 事件列表（节点追加时需合并已有事件）
