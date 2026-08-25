"""
Requirement Nodes

需求评估相关节点：requirement_loop_node, route_after_requirement,
human_input_node, _simple_assessment_fallback。
从 workflow_nodes.py 提取（2026-06-18 workflow-nodes-split-round2 #D）。
"""
import logging
from typing import Dict, List

from context.context_builder import ContextBuilder

from .workflow_state import LeaderWorkflowState
from .node_services import get_services
from .leader_events import _emit, build_fixed_sse_message
from .leader_persistence import _save_leader_message
from .locale_generation import detect_content_locale

logger = logging.getLogger(__name__)


# ==================== 映射表常量 ====================

SCENE_NAMES: Dict[str, str] = {
    'technology': '技术评审',
    'medical': '医疗会诊',
    'investment': '投资分析',
    'legal': '法律咨询',
    'social_hotspot': '社会热点',
    'decision_making': '决策辅助',
    'general': '通用咨询',
}

RISK_LEVEL_MAP: Dict[str, str] = {
    'low': '低风险',
    'medium': '中风险',
    'high': '高风险',
}

SCENE_NAMES_EN: Dict[str, str] = {
    'technology': 'Technology review',
    'medical': 'Medical consultation',
    'investment': 'Investment analysis',
    'legal': 'Legal consultation',
    'social_hotspot': 'Current affairs analysis',
    'decision_making': 'Decision support',
    'general': 'General consultation',
}

RISK_LEVEL_MAP_EN: Dict[str, str] = {
    'low': 'Low risk',
    'medium': 'Medium risk',
    'high': 'High risk',
}

SCORE_DIM_NAMES: Dict[str, str] = {
    # 通用
    'risk': '风险意识', 'risk_awareness': '风险意识',
    'feasibility': '可行性', 'necessity': '必要性',
    'information_c': '信息充分性', 'information_completeness': '信息充分性',
    'technical_detail': '技术细节', 'technical_clarity': '技术清晰度',
    'resource_planning': '资源规划', 'resource_awareness': '资源意识',
    'timeline': '时间规划', 'priority': '优先级',
    'urgency': '紧迫性', 'impact': '影响程度',
    'goal_clarity': '目标明确性', 'expected_results': '预期成果',
    'scope_boundary': '边界范围', 'constraints': '约束条件',
    # 医疗场景
    'symptom_detail': '症状描述', 'medical_history': '病史信息',
    'symptom_description': '症状描述', 'patient_history': '病史信息',
    'examination': '检查结果', 'test_results': '检查结果',
    'medication': '用药情况', 'current_medication': '用药情况',
    'personal_info': '个人情况', 'patient_info': '个人情况',
    'tumor_burden': '肿瘤负荷', 'complication': '并发症',
    'nutrition': '营养状况', 'nutritional_status': '营养状况',
    'treatment_history': '治疗史', 'genetic_info': '基因信息',
    'pain_management': '疼痛管理', 'quality_of_life': '生活质量',
    'prognosis': '预后评估',
    # 投资场景
    'investment_goal': '投资目标', 'risk_preference': '风险偏好',
    'capital_scale': '资金规模', 'investment_horizon': '投资期限',
    'special_constraints': '特殊限制',
    # 法律场景
    'case_background': '案件背景', 'party_identity': '当事人身份',
    'dispute_focus': '争议焦点', 'expected_result': '期望结果',
    'evidence': '证据情况',
    # 决策场景
    'decision_background': '决策背景', 'options': '可选方案',
    'decision_criteria': '决策标准', 'personal_situation': '个人情况',
    'time_pressure': '紧迫程度',
}

SCORE_DIM_NAMES_EN: Dict[str, str] = {
    'risk': 'Risk awareness', 'risk_awareness': 'Risk awareness',
    'feasibility': 'Feasibility', 'necessity': 'Necessity',
    'information_c': 'Information completeness', 'information_completeness': 'Information completeness',
    'technical_detail': 'Technical detail', 'technical_clarity': 'Technical clarity',
    'resource_planning': 'Resource planning', 'resource_awareness': 'Resource awareness',
    'timeline': 'Timeline', 'priority': 'Priority', 'urgency': 'Urgency', 'impact': 'Impact',
    'goal_clarity': 'Goal clarity', 'expected_results': 'Expected outcome',
    'scope_boundary': 'Scope boundary', 'constraints': 'Constraints',
    '目标明确性': 'Goal clarity', '预期成果': 'Expected outcome', '边界范围': 'Scope boundary',
    '约束条件': 'Constraints', '症状描述': 'Symptom details', '病史信息': 'Medical history',
    '检查结果': 'Test results', '用药情况': 'Current medication', '个人情况': 'Personal context',
    '投资目标': 'Investment goal', '风险偏好': 'Risk preference', '资金规模': 'Capital size',
    '投资期限': 'Investment horizon', '特殊限制': 'Special constraints', '案件背景': 'Case background',
    '当事人身份': 'Party identity', '争议焦点': 'Dispute focus', '期望结果': 'Expected outcome',
    '证据情况': 'Evidence', '话题明确性': 'Topic clarity', '分析深度': 'Analysis depth',
    '关注角度': 'Focus angle', '背景了解': 'Background knowledge', '立场倾向': 'Position preference',
    '决策背景': 'Decision context', '可选方案': 'Options', '决策标准': 'Decision criteria',
    '紧迫程度': 'Urgency', '问题清晰度': 'Question clarity', '背景信息': 'Background information',
    '期望深度': 'Expected depth', '应用场景': 'Use case',
}

SCENE_THRESHOLDS: Dict[str, int] = {
    'technology': 60, 'medical': 50, 'investment': 60,
    'legal': 55, 'social_hotspot': 45, 'decision_making': 55, 'general': 50,
}


# ==================== 节点函数 ====================

def requirement_loop_node(state: LeaderWorkflowState) -> Dict:
    """
    需求完善循环节点

    每次调用执行一次评估，边条件控制循环路由

    Args:
        state: 当前状态（含 user_message, history, requirement_loop_count）

    Returns:
        状态更新字典：
        - requirement_passed: bool
        - assessment_result: Dict
        - requirement_questions: List[str] (if not passed)
        - requirement_loop_count: int (+1 if loop)
        - current_phase: str
        - sse_events: List[Dict]
    """
    # 用户已请求停止：立即结束工作流，不做需求评估（避免继续烧 token）
    from .node_services import should_stop_workflow, stop_workflow
    if should_stop_workflow(state):
        logger.info("requirement_loop_node: 检测到停止请求，直接结束工作流")
        stop_event = stop_workflow(state)
        return {
            "current_phase": "execution_stopped",
            "requirement_passed": False,
            "sse_events": state.get("sse_events", []) + [stop_event],
        }

    # 审核决策恢复时跳过需求评估（复用已有评估结果）
    if state.get("skip_to_execution"):
        logger.info("requirement_loop_node: skip_to_execution mode, bypassing assessment")
        return {
            "requirement_passed": True,
            "current_phase": "continuing"
        }

    from .requirement_assessor import RequirementAssessor

    # 获取当前状态
    svc = get_services()
    user_message = state.get("user_message", "")
    history = state.get("history", [])
    session_id = state.get("session_id")
    loop_count = state.get("requirement_loop_count", 0)
    user_answers = state.get("user_answers", [])
    generation_locale = state.get("locale", "zh-CN")
    # 获取所有已问过的问题（累积，用于去重）
    all_asked_questions = state.get("all_asked_questions", [])
    # 获取历史 Q&A 配对（累积，用于评估上下文）
    qa_history = state.get("qa_history", [])

    # 调试日志：追踪历史问题累积
    logger.info(f"requirement_loop_node: loop_count={loop_count}, all_asked_questions_count={len(all_asked_questions)}, "
                f"qa_history_count={len(qa_history)}, "
                f"previous_questions={[q.get('question', '')[:30] for q in all_asked_questions]}")

    # 构建评估消息（原始需求 + 累积历史 Q&A + 当轮回答 + 已问问题去重）
    pack = ContextBuilder.build_for_assessment(
        user_message,
        user_answers or None,
        previous_questions=all_asked_questions if all_asked_questions else None,
        qa_pairs=qa_history if qa_history else None,
    )

    # 初始化评估器（使用注入的服务）
    if svc.llm_service is None:
        logger.warning("LLM service not initialized, using simple assessment")
        # 降级：简单评估
        assessment = _simple_assessment_fallback(pack.task_description, generation_locale)
    else:
        assessor = RequirementAssessor(
            svc.llm_service,
            svc.max_tokens_limit,
            locale=generation_locale,
        )
        try:
            assessment = assessor.assess_requirement(
                message=pack.task_description,
                history=history,
                retry_callback=None,
                context_messages=pack.to_messages(),
                previous_questions=all_asked_questions if all_asked_questions else None,
            )
        except Exception as e:
            logger.error(f"Assessment failed: {e}", exc_info=True)
            assessment = assessor._simple_assessment(pack.task_description)

    # 构建状态更新
    passed = assessment.get("passed", False)
    questions = assessment.get("questions", [])

    logger.info(f"Assessment result: score={assessment.get('score')}, passed={passed}, risk_level={assessment.get('risk_level')}, questions_count={len(questions)}")

    # 合并已有 sse_events + 新事件
    existing_events = state.get("sse_events", [])
    new_events = []

    details = assessment.get("details", {})
    assessment_content_locale = detect_content_locale(
        "\n".join((details.get('analysis', ''), details.get('risk_reason', ''))),
        generation_locale,
    )
    if assessment_content_locale != generation_locale:
        logger.warning(
            "Leader output locale mismatch: session=%s kind=assessment expected=%s actual=%s",
            session_id,
            generation_locale,
            assessment_content_locale,
        )

    # assessment_result 是评估的唯一 SSE 表示，避免与 leader_thinking 重复展示。
    assessment_event = {
        "type": "assessment_result",
        "session_id": session_id,
        "score": assessment.get("score", 50),
        "details": details,
        "passed": passed,
        "risk_level": assessment.get("risk_level", "medium"),
        "content_locale": assessment_content_locale,
    }
    _emit(session_id, assessment_event)
    new_events.append(assessment_event)

    # 持久化评估消息到 Message 表（供历史会话恢复）
    conversation_id = state.get("conversation_id")
    if svc.db_session and conversation_id:
        from schemas.leader import normalize_category_key
        normalized_category = normalize_category_key(assessment.get('category', 'other'))

        if not _save_leader_message(
            db_session=svc.db_session,
            conversation_id=conversation_id,
            session_id=session_id,
            message_type='assessment',
            content={
                'score': assessment.get('score', 50),
                'details': details,
                'risk_level': assessment.get('risk_level', 'medium'),
                'passed': passed,
                'risk_reason': details.get('risk_reason', ''),
                'category': normalized_category,
                'scene': details.get('scene', 'general')
            },
            content_locale=assessment_content_locale,
        ):
            logger.warning(f"Failed to persist assessment message for session {session_id}")

        # 同步评估分数到 LeaderSession（供管理后台和历史查询）
        if session_id:
            try:
                from models import LeaderSession, Conversation
                session_obj = svc.db_session.get(LeaderSession, session_id)
                if session_obj:
                    session_obj.assessment_score = assessment.get('score', 50)
                    session_obj.risk_level = assessment.get('risk_level', 'medium')

                # 【FIX】更新 Conversation 的 category 和 status（修复首页显示问题）
                conversation = svc.db_session.get(Conversation, conversation_id)
                if conversation:
                    conversation.category = normalized_category
                    conversation.status = 'analyzing'
                    logger.info(f"Updated conversation {conversation_id}: category={conversation.category}, status={conversation.status}")

                svc.db_session.commit()
            except Exception as e:
                logger.warning(f"Failed to update session/conversation metadata: {e}")

    # 构建返回状态
    result = {
        "assessment_result": assessment,
        "requirement_passed": passed,
        "current_phase": "requirement_loop",
        "sse_events": existing_events + new_events
    }

    # 将本轮用户的回答与上一轮提出的问题配对，累积到 qa_history
    if user_answers and all_asked_questions:
        answered_count = len(qa_history)
        unanswered_questions = all_asked_questions[answered_count:]
        pairs = []
        for i, answer in enumerate(user_answers):
            question_text = unanswered_questions[i].get('question', '') if i < len(unanswered_questions) else ''
            pairs.append({"question": question_text, "answer": answer})
        if pairs:
            result["qa_history"] = qa_history + pairs
            logger.info(f"requirement_loop_node: accumulated {len(pairs)} qa pairs, "
                        f"total qa_history={len(qa_history) + len(pairs)}")

    # 如果未通过，保存问题（由 human_input_node 发送给用户）
    if not passed:
        result["requirement_questions"] = questions
        # 累积所有已问过的问题（用于下一轮去重）
        new_all_asked = all_asked_questions + questions
        result["all_asked_questions"] = new_all_asked
        logger.info(f"requirement_loop_node: new questions count={len(questions)}, "
                    f"all_asked_questions updated to {len(new_all_asked)}")

    return result


def route_after_requirement(state: LeaderWorkflowState) -> str:
    """
    需求评估后路由条件

    Args:
        state: 当前状态

    Returns:
        - "team_form": loop_count >= 3 或 (passed + score >= threshold) 或 无问题可追问
        - "human_input": loop_count < 3 且 (not passed 或 score < threshold) 且有问题可追问
        - "end": 用户已请求停止
    """
    # 停止请求：直接结束工作流
    if state.get("current_phase") == "execution_stopped":
        return "end"

    passed = state.get("requirement_passed", False)
    loop_count = state.get("requirement_loop_count", 0)
    questions = state.get("requirement_questions", [])
    assessment = state.get("assessment_result", {})
    score = assessment.get("score", 50)

    # 【调试日志】路由决策全貌
    logger.warning(f"[ROUTE_DEBUG] loop_count={loop_count}, passed={passed}, score={score}, "
                   f"questions_count={len(questions)}, assessment_keys={list(assessment.keys())}")

    # 前置检查：超次数强制通过
    if loop_count >= 3:
        logger.warning(f"[ROUTE_DEBUG] Exceeded max rounds ({loop_count}), forcing team_form")
        return "team_form"

    # score 阈值二次校验（防御 LLM 低分却 passed=True）
    # 模板自定义阈值优先于场景阈值
    scene = assessment.get("details", {}).get("scene", "general")
    state_threshold = state.get("assessment_threshold")
    threshold = state_threshold if state_threshold is not None else SCENE_THRESHOLDS.get(scene, 50)

    logger.warning(f"[ROUTE_DEBUG] scene={scene}, threshold={threshold}, score_check={score >= threshold}")

    if passed and score >= threshold:
        logger.warning(f"[ROUTE_DEBUG] Passed and score >= threshold, returning team_form")
        return "team_form"

    # 未通过或分数不达标，检查是否有问题可问
    if not questions:
        logger.warning(f"[ROUTE_DEBUG] No questions despite low score, forcing team_form")
        return "team_form"

    logger.warning(f"[ROUTE_DEBUG] Routing to human_input")
    return "human_input"


def human_input_node(state: LeaderWorkflowState) -> Dict:
    """
    用户输入等待节点

    发送问题给用户并终止工作流，等待用户通过 continue_leader_workflow 提交答案。

    Args:
        state: 当前状态（含 requirement_questions, requirement_loop_count）

    Returns:
        状态更新字典：
        - requirement_loop_count: int (+1)
        - current_phase: str
        - sse_events: List[Dict]
    """
    loop_count = state.get("requirement_loop_count", 0)
    session_id = state.get("session_id")
    questions = state.get("requirement_questions", [])
    generation_locale = state.get("locale", "zh-CN")
    existing_events = state.get("sse_events", [])

    # 如果 questions 为空，记录错误并跳过追问（LLM 应该返回有效问题）
    if not questions:
        logger.error(f"human_input_node: no questions from LLM, session_id={session_id}")
        # 直接进入下一阶段，不追问
        return {
            "requirement_loop_count": loop_count + 1,
            "current_phase": "team_form",
            "sse_events": existing_events
        }

    # 验证每个问题都有有效选项
    for q in questions:
        opts = q.get("options", [])
        if not opts or len(opts) < 2:
            logger.error(f"human_input_node: question missing valid options: {q}")
            # 跳过追问
            return {
                "requirement_loop_count": loop_count + 1,
                "current_phase": "team_form",
                "sse_events": existing_events
            }

    new_events = []
    question_visible_text = "\n".join(
        str(value)
        for question in questions
        for value in [question.get("question", ""), *(question.get("options", []) or [])]
    )
    question_content_locale = detect_content_locale(question_visible_text, generation_locale)
    if question_content_locale != generation_locale:
        logger.warning(
            "Leader output locale mismatch: session=%s kind=question expected=%s actual=%s",
            session_id,
            generation_locale,
            question_content_locale,
        )

    # 发送问题事件（触发前端对话框）
    question_event = {
        "type": "leader_question",
        "session_id": session_id,
        "questions": questions,
        "content_locale": question_content_locale,
    }
    _emit(session_id, question_event)
    new_events.append(question_event)

    # 持久化问题消息到 Message 表（供历史会话恢复）
    conversation_id = state.get("conversation_id")
    svc = get_services()
    if svc.db_session and conversation_id:
        if not _save_leader_message(
            db_session=svc.db_session,
            conversation_id=conversation_id,
            session_id=session_id,
            message_type='question',
            content={'questions': questions},
            content_locale=question_content_locale,
        ):
            logger.warning(f"Failed to persist question message for session {session_id}")

    # 【修复追问卡死】持久化 loop_count + session.state 到 LeaderSession
    new_loop_count = loop_count + 1
    if svc.db_session and session_id:
        from models import LeaderSession
        session_obj = svc.db_session.get(LeaderSession, session_id)
        if session_obj:
            session_obj.requirement_loop_count = new_loop_count
            session_obj.state = "questioning"
            from services.decision_run_service import DecisionRunService
            DecisionRunService(svc.db_session).sync_from_leader_session(session_id)
            svc.db_session.commit()
            logger.info(f"human_input_node: persisted requirement_loop_count={new_loop_count}, state=questioning to session {session_id}")

    # 发送等待提示
    fixed_message = build_fixed_sse_message(
        generation_locale,
        "leader.phase.waiting_answers",
    )
    thinking_event = {
        "type": "leader_thinking",
        "session_id": session_id,
        "phase": "human_input",
        "content": fixed_message["message"],
        "content_locale": generation_locale,
        **fixed_message,
    }
    _emit(session_id, thinking_event)
    new_events.append(thinking_event)

    return {
        "requirement_loop_count": new_loop_count,
        "current_phase": "human_input",
        "sse_events": existing_events + new_events
    }


def _simple_assessment_fallback(message: str, locale: str = "zh-CN") -> Dict:
    """
    简单评估降级方案（无 LLM 服务时 - 仅用于完全失败场景）
    统一使用语言无关规则；医疗场景保守降级并生成追问
    """
    from .requirement_assessor import simple_assessment_fallback

    return simple_assessment_fallback(message, locale)
