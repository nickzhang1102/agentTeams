"""
Team Formation Nodes

团队组建与 DAG 执行计划生成相关节点。
从 workflow_nodes.py 提取（2026-06-18 workflow-nodes-split-round2 #D）。
"""
import logging
from typing import Dict, List

from .workflow_state import LeaderWorkflowState
from .node_services import get_services
from .leader_events import _emit, build_fixed_sse_message
from .leader_persistence import _save_leader_message
from .locale_generation import resolve_agent_display_name

logger = logging.getLogger(__name__)


def team_form_dag_node(state: LeaderWorkflowState) -> Dict:
    """
    团队组建 + DAG 执行计划生成节点

    调用 TeamFormer 获取候选 Agent，再调用 DAGPlanner 生成执行计划。

    Args:
        state: 当前状态（含 user_message, assessment_result）

    Returns:
        状态更新字典：
        - selected_agents: List[Dict]
        - dag_execution_plan: Dict
        - current_phase: str
        - sse_events: List[Dict]
    """
    # 用户已请求停止：跳过团队组建（尽量减少后续 token 消耗）
    from .node_services import should_stop_workflow, stop_workflow
    if should_stop_workflow(state):
        logger.info("team_form_dag_node: 检测到停止请求，跳过团队组建")
        stop_event = stop_workflow(state)
        return {
            "current_phase": "execution_stopped",
            "sse_events": state.get("sse_events", []) + [stop_event],
        }

    # skip_to_execution 模式分支
    if state.get("skip_to_execution"):
        pre_selected = state.get("pre_selected_agents", [])
        if pre_selected:
            # 快速模式：从 pre_selected_agents 构建团队
            return _build_team_from_presets(state, pre_selected)
        else:
            # 恢复执行：依赖 DB 中已有的 selected_agents 和 dag_execution_plan
            logger.info("team_form_dag_node: skip_to_execution mode, bypassing team formation")
            return {"current_phase": "continuing"}

    from .team_former import TeamFormer
    from .dag_planner import DAGPlanner

    # 获取当前状态
    svc = get_services()
    user_message = state.get("user_message", "")
    session_id = state.get("session_id")
    assessment_result = state.get("assessment_result", {})
    existing_events = state.get("sse_events", [])

    if svc.db_session is not None and session_id:
        from services.decision_run_service import DecisionRunService
        DecisionRunService(svc.db_session).set_stage(session_id, 'team_form')
        svc.db_session.commit()

    # 从评估结果获取参数
    risk_level = assessment_result.get("risk_level", "medium")
    scene = assessment_result.get("scene", "general")
    category = assessment_result.get("category", "")

    new_events = []
    generation_locale = state.get("locale", "zh-CN")

    # 团队策略（从 TeamFormer 结果或 role_description 提取）
    team_strategy = ''

    # 实时推送团队组建开始事件（不等节点结束）
    fixed_message = build_fixed_sse_message(
        generation_locale,
        "leader.phase.forming_team",
    )
    team_start_event = {
        "type": "team_forming",
        "session_id": session_id,
        "phase": "team_form_dag",
        "content": fixed_message["message"],
        **fixed_message,
    }
    _emit(session_id, team_start_event)
    new_events.append(team_start_event)

    # 初始化服务
    if svc.llm_service is None or svc.agent_reader is None:
        logger.warning("Services not initialized, using fallback team selection")
        selected_agents = _fallback_team_selection(scene, risk_level, generation_locale)
    else:
        # 调用 TeamFormer 组建团队
        team_former = TeamFormer(
            svc.llm_service,
            svc.agent_reader,
            svc.max_tokens_limit,
            locale=generation_locale,
        )
        try:
            team_result = team_former.form_team(
                message=user_message,
                risk_level=risk_level,
                retry_callback=None
            )
            selected_agents = team_result.get("selected_agents", [])
            team_strategy = team_result.get("team_strategy", '')
        except Exception as e:
            logger.error(f"TeamFormer failed: {e}", exc_info=True)
            selected_agents = _fallback_team_selection(scene, risk_level, generation_locale)

    # 检查是否有 Agent
    if not selected_agents:
        logger.warning("No agents selected, creating fallback team")
        selected_agents = _fallback_team_selection(scene, risk_level, generation_locale)

    # 生成 DAG 执行计划
    if svc.db_session is None or svc.agent_reader is None:
        logger.warning("DB/Reader not initialized, using simple plan")
        dag_plan = _simple_dag_plan(selected_agents)
    else:
        dag_planner = DAGPlanner(svc.db_session, svc.agent_reader)
        try:
            dag_plan = dag_planner.plan_from_requirement(
                selected_agents=selected_agents,
                risk_level=risk_level,
                scene=scene,
                category=category
            )
        except Exception as e:
            logger.error(f"DAGPlanner failed: {e}", exc_info=True)
            dag_plan = _simple_dag_plan(selected_agents)

    # 降级：从 selected_agents 的 role_description 提取策略摘要
    if not team_strategy and selected_agents:
        roles = [a.get('role_description', '') for a in selected_agents if a.get('role_description')]
        team_strategy = '；'.join(roles) if roles else ''

    # 持久化团队配置 + 推送事件（公共逻辑）
    persist_events = _persist_team_and_emit(
        svc=svc,
        session_id=session_id,
        conversation_id=state.get("conversation_id"),
        selected_agents=selected_agents,
        dag_plan=dag_plan,
        team_strategy=team_strategy,
        user_message=user_message,
        mode='parallel',
        locale=generation_locale,
    )

    return {
        "selected_agents": selected_agents,
        "dag_execution_plan": dag_plan,
        "current_phase": "team_form_dag",
        "sse_events": existing_events + new_events + persist_events
    }


def _build_team_from_presets(state: LeaderWorkflowState, agent_ids: List[str]) -> Dict:
    """从预选 agent_id 列表构建团队（快速模式）。

    跳过 TeamFormer，直接从 DB 获取元数据构建 selected_agents，再生成 DAG 计划。
    """
    from .dag_planner import DAGPlanner

    svc = get_services()
    session_id = state.get("session_id")
    conversation_id = state.get("conversation_id")
    user_message = state.get("user_message", "")
    existing_events = state.get("sse_events", [])

    if svc.db_session is not None and session_id:
        from services.decision_run_service import DecisionRunService
        DecisionRunService(svc.db_session).set_stage(session_id, 'team_form')
        svc.db_session.commit()
    new_events = []
    generation_locale = state.get("locale", "zh-CN")

    # 推送团队组建开始事件
    fixed_message = build_fixed_sse_message(
        generation_locale,
        "leader.phase.forming_preset_team",
    )
    team_start_event = {
        "type": "team_forming",
        "session_id": session_id,
        "phase": "team_form_dag",
        "content": fixed_message["message"],
        **fixed_message,
    }
    _emit(session_id, team_start_event)
    new_events.append(team_start_event)

    # 从 agent_reader 获取元数据构建 selected_agents
    selected_agents = []
    missing_agents = []
    if svc.agent_reader:
        for agent_id in agent_ids:
            metadata = svc.agent_reader.get_agent_metadata(agent_id)
            if metadata:
                selected_agents.append({
                    "agent_id": agent_id,
                    "agent_name": resolve_agent_display_name(
                        agent_id,
                        metadata.get("name"),
                        generation_locale,
                        metadata.get("is_system"),
                    ),
                    "role_description": metadata.get("description", ""),
                })
            else:
                logger.warning(f"Agent '{agent_id}' metadata not found, using raw id")
                missing_agents.append(agent_id)
                selected_agents.append({
                    "agent_id": agent_id,
                    "agent_name": resolve_agent_display_name(agent_id, agent_id, generation_locale),
                    "role_description": "",
                })
    else:
        logger.warning("agent_reader not available, falling back to raw agent ids")
        for agent_id in agent_ids:
            selected_agents.append({
                "agent_id": agent_id,
                "agent_name": resolve_agent_display_name(agent_id, agent_id, generation_locale),
                "role_description": "",
            })

    # 生成 DAG 执行计划（快速模式无评估数据，使用默认参数；优先级规则仍可按 agent_id 匹配）
    if svc.db_session and svc.agent_reader:
        dag_planner = DAGPlanner(svc.db_session, svc.agent_reader)
        try:
            dag_plan = dag_planner.plan_from_requirement(
                selected_agents=selected_agents,
                risk_level="medium",
                scene="general",
                category=""
            )
        except Exception as e:
            logger.error(f"DAGPlanner failed in quick mode: {e}", exc_info=True)
            dag_plan = _simple_dag_plan(selected_agents)
    else:
        dag_plan = _simple_dag_plan(selected_agents)

    # 提取策略摘要
    roles = [a.get('role_description', '') for a in selected_agents if a.get('role_description')]
    team_strategy = (
        'Quick mode team' if generation_locale == 'en-US' else
        '；'.join(roles) if roles else '快速模式团队'
    )

    # 持久化团队配置 + 推送事件（公共逻辑）
    persist_events = _persist_team_and_emit(
        svc=svc,
        session_id=session_id,
        conversation_id=conversation_id,
        selected_agents=selected_agents,
        dag_plan=dag_plan,
        team_strategy=team_strategy,
        user_message=user_message,
        mode='quick',
        locale=generation_locale,
    )

    result = {
        "selected_agents": selected_agents,
        "dag_execution_plan": dag_plan,
        "current_phase": "team_form_dag",
        "sse_events": existing_events + new_events + persist_events
    }
    if missing_agents:
        result["missing_agents"] = missing_agents
    return result


def _persist_team_and_emit(
    svc,
    session_id: int,
    conversation_id: int,
    selected_agents: List[Dict],
    dag_plan: Dict,
    team_strategy: str,
    user_message: str,
    mode: str = 'parallel',
    locale: str = 'zh-CN',
) -> List[Dict]:
    """推送团队组建 SSE 事件 + 持久化 team_config 到 DB。

    Returns:
        本次创建的 SSE 事件列表（由调用方合并到 sse_events）
    """
    is_english = locale == 'en-US'
    team_label = ('Quick team' if is_english else '快速团队') if mode == 'quick' else ('Smart team' if is_english else '智能团队')
    fallback_desc = (
        'Quick mode team' if is_english else '快速模式团队'
    ) if mode == 'quick' else (
        'Expert team formed for the request' if is_english else '为需求智能组建的专家团队'
    )
    description = team_strategy or fallback_desc
    new_events = []

    # selection_complete 事件（前端 handleTeamForming 依赖）
    selection_event = {
        "type": "team_forming",
        "session_id": session_id,
        "phase": "selection_complete",
        "content": description,
        "selected_agents": selected_agents,
        "content_locale": locale,
    }
    _emit(session_id, selection_event)
    new_events.append(selection_event)

    # team_ready 事件（前端 handleTeamReady 依赖）
    team_ready_event = {
        "type": "team_ready",
        "session_id": session_id,
        "team": {
            "name": f"{team_label} - {user_message[:20]}",
            "description": description,
            "agents": selected_agents,
            "dag_plan": dag_plan,
            "execution_order": _describe_execution_order(dag_plan, locale),
        },
        "content_locale": locale,
    }
    _emit(session_id, team_ready_event)
    new_events.append(team_ready_event)

    # 持久化 team_config 消息 + 更新 LeaderSession.selected_agents
    selected_agent_ids = [a.get('agent_id', '') for a in selected_agents]
    if svc.db_session and conversation_id:
        if not _save_leader_message(
            db_session=svc.db_session,
            conversation_id=conversation_id,
            session_id=session_id,
            message_type='team_config',
            content={
                'agents': selected_agent_ids,
                'agent_details': selected_agents,
                'mode': mode,
                'team_strategy': team_strategy,
                'dag_plan': dag_plan,
            },
            content_locale=locale,
        ):
            logger.warning(f"Failed to persist team_config message for session {session_id}，workflow resume may fail")

        from models import LeaderSession
        leader_session = svc.db_session.get(LeaderSession, session_id)
        if leader_session:
            leader_session.set_selected_agents_list(selected_agent_ids)
            svc.db_session.commit()
            logger.info(f"Updated session {session_id} (mode={mode}): agents={selected_agent_ids}")

    return new_events


def _fallback_team_selection(scene: str, risk_level: str, locale: str = 'zh-CN') -> List[Dict]:
    """
    降级团队选择（服务不可用时）

    Args:
        scene: 场景类型
        risk_level: 风险等级

    Returns:
        默认 Agent 列表
    """
    is_english = locale == 'en-US'
    # 根据场景选择默认 Agent（使用实际存在的 agent_id）
    if scene == "medical":
        return [
            {
                "agent_id": "general-practice-expert",
                "agent_name": resolve_agent_display_name(
                    "general-practice-expert", "全科专家", locale
                ),
                "role_description": "Comprehensive assessment" if is_english else "综合评估",
            },
        ]
    elif scene == "technology":
        agents = [
            {
                "agent_id": "fullstack-dhh",
                "agent_name": resolve_agent_display_name(
                    "fullstack-dhh", "全栈技术主管", locale
                ),
                "role_description": "Technical solution design" if is_english else "技术方案设计",
            },
        ]
        if risk_level == "high":
            agents.append({
                "agent_id": "critic-munger",
                "agent_name": resolve_agent_display_name(
                    "critic-munger", "逆向思考顾问", locale
                ),
                "role_description": "Plan review" if is_english else "方案审核"
            })
        return agents
    else:
        return [
            {
                "agent_id": "general-practice-expert",
                "agent_name": resolve_agent_display_name(
                    "general-practice-expert", "全科专家", locale
                ),
                "role_description": "Comprehensive analysis" if is_english else "综合分析",
            },
        ]


def _simple_dag_plan(selected_agents: List[Dict]) -> Dict:
    """
    简单 DAG 计划（所有 Agent 并行）

    Args:
        selected_agents: Agent 列表

    Returns:
        DAG 执行计划
    """
    nodes = []
    agents_in_batch = []

    for i, agent in enumerate(selected_agents, 1):
        agent_id = agent.get("agent_id", "")
        nodes.append({
            "id": f"agent_{i}",
            "agent_id": agent_id,
            "agent_name": agent.get("agent_name", ""),
            "role_description": agent.get("role_description", ""),
            "priority": 50,
            "priority_source": "default"
        })
        agents_in_batch.append(agent_id)

    return {
        "nodes": nodes,
        "execution_batches": [{"priority": 50, "agents": agents_in_batch}],
        "matched_rules": []
    }


def _describe_execution_order(dag_plan: Dict, locale: str = 'zh-CN') -> str:
    """
    生成执行顺序描述

    Args:
        dag_plan: DAG 执行计划

    Returns:
        执行顺序描述文本
    """
    batches = dag_plan.get("execution_batches", [])
    lines = []
    for i, batch in enumerate(batches, 1):
        agents_str = ", ".join(batch["agents"])
        if len(batch["agents"]) > 1:
            lines.append(
                f"Batch {i} (priority={batch['priority']}, parallel): {agents_str}"
                if locale == 'en-US' else
                f"批次{i}（priority={batch['priority']}，并行）：{agents_str}"
            )
        else:
            lines.append(
                f"Batch {i} (priority={batch['priority']}): {agents_str}"
                if locale == 'en-US' else
                f"批次{i}（priority={batch['priority']}）：{agents_str}"
            )
    return "\n".join(lines)
