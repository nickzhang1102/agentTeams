"""
Summarize Nodes

结果汇总相关节点：summarize_node, _build_summary_prompt, _call_llm_for_summary, _fallback_summary。
从 workflow_nodes.py 提取（2026-06-18 workflow-nodes-split-round2 #D）。
"""
import asyncio
import logging
import re
import time
from datetime import datetime
from typing import Dict, Optional, Any, List

from utils.async_utils import safe_async_run
from utils.time_utils import utcnow_naive
from schemas.leader import FinalReportResult

from .workflow_state import LeaderWorkflowState
from .node_services import get_services, should_stop_workflow, stop_workflow
from .leader_events import _emit, build_fixed_sse_message
from .leader_persistence import _persist_final_report
from .locale_generation import (
    OutputLengthPolicy,
    build_output_locale_instruction,
    detect_content_locale,
    get_output_length_policy,
    resolve_generation_locale,
)
from .report_structures import final_report_structured_payload, final_report_summary_payload

logger = logging.getLogger(__name__)

# 最终综合报告是面向用户的完整交付物，给足长报告空间，但避免误用模型理论最大输出上限。
_FINAL_REPORT_MAX_TOKENS = 12288
_FINAL_REPORT_TIMEOUT_SECONDS = 120.0
_SUMMARY_AGENT_CONTENT_CHAR_LIMIT = 6000
_SUMMARY_CRITIC_CONTENT_CHAR_LIMIT = 8000
_SUMMARY_LIST_ITEM_LIMIT = 6
_SUMMARY_CONFIDENCE_THRESHOLD = 0.4  # 低于此置信度的摘要视为不可用，回退全文裁剪
_FINAL_REPORT_MIN_HEADINGS = 3


def summarize_node(state: LeaderWorkflowState) -> Dict:
    """结果汇总节点

    调用 LLM 生成最终汇总报告，持久化到数据库。

    Args:
        state: 当前状态（含 agent_results, user_message, session_id）

    Returns:
        状态更新字典：
        - final_report: str（Markdown 格式）
        - current_phase: str
        - sse_events: List[Dict]
    """
    # 获取当前状态
    svc = get_services()
    agent_results = state.get("agent_results", [])
    user_message = state.get("user_message", "")
    qa_history = state.get("qa_history", [])
    session_id = state.get("session_id")
    existing_events = state.get("sse_events", [])
    generation_locale = resolve_generation_locale(session_locale=state.get("locale"))
    length_policy = get_output_length_policy(generation_locale)

    if svc.db_session is not None and session_id:
        from services.decision_run_service import DecisionRunService
        DecisionRunService(svc.db_session).set_stage(session_id, 'synthesis')
        svc.db_session.commit()

    new_events = []
    start_time = time.time()

    # 用户已请求停止：跳过 LLM 报告生成，直接给出停止反馈并收尾（避免烧 token）
    if should_stop_workflow(state):
        logger.info("summarize_node: 检测到停止请求，跳过最终报告生成")
        stop_event = stop_workflow(state)
        _emit(session_id, stop_event)
        return {
            "current_phase": "execution_stopped",
            "quality_status": "stopped",
            "sse_events": existing_events + [stop_event],
        }

    # 发送汇总开始事件
    fixed_message = build_fixed_sse_message(
        generation_locale,
        "leader.phase.summarizing",
    )
    summarizing_event = {
        "type": "leader_summarizing",
        "session_id": session_id,
        "content": fixed_message["message"],
        **fixed_message,
    }
    _emit(session_id, summarizing_event)
    new_events.append(summarizing_event)

    # 边界场景：空 Agent 结果
    if not agent_results:
        logger.warning("No agent results to summarize")
        final_report = (
            "## Final Recommendation\n\nNo expert analysis results were available, so a final report could not be generated."
            if generation_locale == "en-US"
            else "## 综合建议\n\n抱歉，没有收到任何专家的分析结果，无法生成综合报告。"
        )
        content_locale = detect_content_locale(final_report, generation_locale)
        completed_at = utcnow_naive()
        total_time = _calculate_session_total_time(
            svc.db_session,
            session_id,
            completed_at,
            fallback_elapsed=time.time() - start_time,
        )
        # 即使无 agent 结果也必须先持久化报告并标记完成。
        if svc.db_session is not None and session_id is not None:
            final_report_record = _persist_final_report(
                db_session=svc.db_session,
                session_id=session_id,
                report=final_report,
                content_locale=content_locale,
                completed_at=completed_at,
                state=state,
                quality_status="degraded",
                degradation_reasons=["no_agent_results"],
            )
            if final_report_record is None and should_stop_workflow(state):
                logger.info("summarize_node: 空结果报告持久化被停止请求阻止")
                stop_event = stop_workflow(state)
                _emit(session_id, stop_event)
                return {
                    "current_phase": "execution_stopped",
                    "quality_status": "stopped",
                    "sse_events": existing_events + new_events + [stop_event],
                }

        empty_event = {
            "type": "final_report",
            "session_id": session_id,
            "report": final_report,
            "content_locale": content_locale,
            "total_time": total_time
        }
        _emit(session_id, empty_event)
        new_events.append(empty_event)

        return {
            "final_report": final_report,
            "current_phase": "summarize_complete",
            "sse_events": existing_events + new_events
        }

    # 检查是否有成功的 agent 结果
    successful_results = [r for r in agent_results if r.get("success")]
    if not successful_results:
        logger.warning("All agent results failed")
        final_report = (
            "## Final Recommendation\n\nAll expert executions failed, so a final report could not be generated."
            if generation_locale == "en-US"
            else "## 综合建议\n\n所有专家的执行都失败了，无法生成综合报告。"
        )
        content_locale = detect_content_locale(final_report, generation_locale)
        completed_at = utcnow_naive()
        total_time = _calculate_session_total_time(
            svc.db_session,
            session_id,
            completed_at,
            fallback_elapsed=time.time() - start_time,
        )
        # 即使全部失败也必须先持久化报告并标记完成。
        if svc.db_session is not None and session_id is not None:
            final_report_record = _persist_final_report(
                db_session=svc.db_session,
                session_id=session_id,
                report=final_report,
                content_locale=content_locale,
                completed_at=completed_at,
                state=state,
                quality_status="degraded",
                degradation_reasons=["all_agent_results_failed"],
            )
            if final_report_record is None and should_stop_workflow(state):
                logger.info("summarize_node: 全失败报告持久化被停止请求阻止")
                stop_event = stop_workflow(state)
                _emit(session_id, stop_event)
                return {
                    "current_phase": "execution_stopped",
                    "quality_status": "stopped",
                    "sse_events": existing_events + new_events + [stop_event],
                }

        failed_event = {
            "type": "final_report",
            "session_id": session_id,
            "report": final_report,
            "content_locale": content_locale,
            "total_time": total_time
        }
        _emit(session_id, failed_event)
        new_events.append(failed_event)

        return {
            "final_report": final_report,
            "current_phase": "summarize_complete",
            "sse_events": existing_events + new_events
        }

    # 检测是否包含逆向思考顾问
    has_critic = any(
        "critic" in r.get("agent_id", "").lower() or "munger" in r.get("agent_id", "").lower()
        for r in successful_results
    )

    # 分离逆向思考顾问和其他专家的结果
    critic_result = None
    other_results = []
    for result in successful_results:
        if "critic" in result.get("agent_id", "").lower() or "munger" in result.get("agent_id", "").lower():
            critic_result = result
        else:
            other_results.append(result)

    degraded_results = [
        result for result in successful_results
        if result.get("quality_status") == "degraded"
    ]
    degradation_reasons = list(dict.fromkeys(
        str(result.get("degradation_reason") or "Agent 执行发生降级").strip()
        for result in degraded_results
    ))
    quality_status = "degraded" if degraded_results else "normal"

    all_evidence = _collect_final_evidence(successful_results)
    available_evidence_ids = {
        item.get("evidence_id") for item in all_evidence if item.get("evidence_id")
    }
    target_units = _adaptive_final_report_target_units(
        successful_results,
        length_policy=length_policy,
        user_message=user_message,
        qa_history=qa_history,
    )
    if svc.llm_service is not None:
        target_units = _fit_target_units_to_output_budget(
            target_units,
            length_policy,
            svc.llm_service,
        )

    # 构建 prompt（传入原始用户需求 + 追问回答历史）
    prompt = _build_summary_prompt(
        other_results,
        critic_result,
        has_critic,
        user_message,
        qa_history,
        target_units=target_units,
        length_policy=length_policy,
    )

    # 调用 LLM 生成报告
    final_summary = None
    structured_report = None
    if svc.llm_service is None:
        logger.warning("LLM service not initialized, using fallback summary")
        final_report = _fallback_summary(
            other_results,
            critic_result,
            has_critic,
            locale=generation_locale,
        )
    else:
        try:
            final_report, final_summary, structured_report = _call_llm_for_summary(
                prompt,
                target_units=target_units,
                length_policy=length_policy,
                available_evidence_ids=available_evidence_ids,
            )
        except Exception as e:
            logger.error(f"LLM call for summary failed: {e}", exc_info=True)
            final_report = _fallback_summary(
                other_results,
                critic_result,
                has_critic,
                locale=generation_locale,
            )
            final_summary = None
            structured_report = None

    # 停止请求可能在最终汇总 LLM 调用期间到达。节点入口检查只能避免
    # 尚未开始的调用；这里必须在任何报告/证据持久化前再次检查，避免继续
    # 发布迟到结果。持久化层另有同行锁兜底，覆盖检查后的窄竞态窗口。
    if should_stop_workflow(state):
        logger.info("summarize_node: 汇总生成期间收到停止请求，丢弃迟到报告")
        stop_event = stop_workflow(state)
        _emit(session_id, stop_event)
        return {
            "current_phase": "execution_stopped",
            "quality_status": "stopped",
            "sse_events": existing_events + new_events + [stop_event],
        }

    # 计算 Token 使用量（汇总 LLM 调用）
    # 注：这里暂不统计汇总 Token，后续可从 LLM 响应中提取

    # 持久化到数据库
    evidence_map = _filter_evidence_map_for_report(
        all_evidence,
        final_report,
        structured_report,
    )
    if structured_report is not None:
        structured_report["source_quality_status"] = quality_status
        structured_report["source_degradation_reasons"] = degradation_reasons
    content_locale = detect_content_locale(
        _final_report_visible_text(final_report, final_summary, structured_report),
        generation_locale,
    )
    if content_locale != generation_locale:
        logger.warning(
            "Leader output locale mismatch: session=%s kind=final_report expected=%s actual=%s",
            session_id,
            generation_locale,
            content_locale,
        )
    final_report_record = None
    completed_at = utcnow_naive()
    if svc.db_session is not None and session_id is not None:
        final_report_record = _persist_final_report(
            db_session=svc.db_session,
            session_id=session_id,
            report=final_report,
            content_locale=content_locale,
            completed_at=completed_at,
            executive_summary=final_summary,
            structured_report=structured_report,
            evidence_map=evidence_map,
            state=state,
            quality_status="degraded" if degraded_results else "passed",
            degradation_reasons=["agent_source_degraded"] if degraded_results else [],
            evidence_context_dropped_count=0,
        )
        # 停止可能发生在上一次检查之后，并由持久化层的行锁裁决。此时
        # _persist_final_report 返回 None，必须发送停止事件而不是 final_report。
        if final_report_record is None and should_stop_workflow(state):
            logger.info("summarize_node: 最终报告持久化被停止请求阻止")
            stop_event = stop_workflow(state)
            _emit(session_id, stop_event)
            return {
                "current_phase": "execution_stopped",
                "quality_status": "stopped",
                "sse_events": existing_events + new_events + [stop_event],
            }
        if (
            isinstance(structured_report, dict)
            and structured_report.get("source_quality_status") == "degraded"
        ):
            quality_status = "degraded"
            degradation_reasons = list(dict.fromkeys(
                structured_report.get("source_degradation_reasons") or []
            ))

        # 对话结束后异步提取用户记忆（不阻塞 SSE）
        user_id = state.get("user_id")
        conversation_id = state.get("conversation_id")
        if user_id and conversation_id:
            try:
                import threading
                from services.memory_service import MemoryService
                from db import get_db_session

                async def _extract_memories():
                    mem_db = get_db_session()
                    try:
                        llm_svc = svc.llm_service
                        mem_svc = MemoryService(db_session=mem_db, llm_service=llm_svc)
                        history = state.get("history", [])
                        await mem_svc.extract_from_conversation(
                            user_id=user_id,
                            conversation_id=conversation_id,
                            messages=history,
                        )
                        mem_db.commit()
                    except Exception:
                        mem_db.rollback()
                        logger.warning("Background memory extraction failed", exc_info=True)
                    finally:
                        mem_db.close()

                # 同步上下文中无法用 asyncio.create_task，改用后台线程
                threading.Thread(
                    target=lambda: asyncio.run(_extract_memories()),
                    daemon=True,
                ).start()
            except Exception:
                logger.warning("Failed to schedule memory extraction", exc_info=True)

    # 计算总耗时：SSE 实时事件与历史接口统一使用 session started_at -> completed_at。
    total_time = _calculate_session_total_time(
        svc.db_session,
        session_id,
        completed_at,
        fallback_elapsed=time.time() - start_time,
    )

    final_report_event = {
        "type": "final_report",
        "session_id": session_id,
        "report": final_report,
        "content_locale": content_locale,
        "total_time": total_time,
        "quality_status": quality_status,
    }
    if degradation_reasons:
        final_report_event["degradation_reasons"] = degradation_reasons
    if final_summary is not None:
        final_report_event["summary"] = final_summary
    if structured_report is not None:
        final_report_event["structured_report"] = structured_report
    if evidence_map:
        final_report_event["evidence_map"] = evidence_map
    if final_report_record is not None:
        final_report_event["id"] = final_report_record.id

    # 发送汇总完成事件
    _emit(session_id, final_report_event)
    new_events.append(final_report_event)

    return {
        "final_report": final_report,
        "current_phase": "summarize_complete",
        "quality_status": quality_status,
        "degradation_reasons": degradation_reasons,
        "sse_events": existing_events + new_events
    }


def _calculate_session_total_time(
    db_session: Any,
    session_id: Optional[int],
    completed_at: datetime,
    fallback_elapsed: float,
) -> float:
    """Return whole-session elapsed time, falling back to local node duration."""
    if db_session is not None and session_id is not None:
        try:
            from models import LeaderSession
            session = db_session.get(LeaderSession, session_id)
            started_at = getattr(session, "started_at", None) if session else None
            if started_at:
                if started_at.tzinfo is not None:
                    started_at = started_at.replace(tzinfo=None)
                if completed_at.tzinfo is not None:
                    completed_at = completed_at.replace(tzinfo=None)
                return max(round((completed_at - started_at).total_seconds(), 2), 0)
        except Exception:
            logger.warning("Failed to calculate session total_time; using fallback", exc_info=True)
    return max(round(fallback_elapsed, 2), 0)


def _collect_final_evidence(agent_results: List[Dict]) -> List[Dict]:
    """Collect Agent evidence maps for the final report payload."""
    evidence: List[Dict] = []
    seen = set()
    for result in agent_results:
        for item in result.get("evidence_map", []) or []:
            if not isinstance(item, dict):
                continue
            evidence_id = item.get("evidence_id")
            if evidence_id and evidence_id in seen:
                continue
            if evidence_id:
                seen.add(evidence_id)
            evidence.append(item)
    return evidence


def _adaptive_final_report_target_units(
    agent_results: List[Dict],
    length_policy: OutputLengthPolicy,
    user_message: str = "",
    qa_history: Optional[List[Dict]] = None,
) -> int:
    """Scale locale-aware report depth with Agent count, evidence, and bounded input size."""
    agent_count = max(1, len(agent_results))
    evidence_count = len(_collect_final_evidence(agent_results))
    input_chars = sum(
        min(len(str(result.get("content") or result.get("output") or "")), 8000)
        for result in agent_results
    )
    input_chars += len(user_message or "")
    input_chars += sum(
        len(str(item.get("question") or "")) + len(str(item.get("answer") or ""))
        for item in (qa_history or [])
        if isinstance(item, dict)
    )
    return length_policy.target_units(
        agent_count=agent_count,
        evidence_count=evidence_count,
        input_size=input_chars,
    )


def _filter_evidence_map_for_report(
    evidence_map: List[Dict],
    markdown_report: str,
    structured_report: Optional[Dict],
) -> List[Dict]:
    """Keep only evidence that the final report actually cites."""
    available_ids = {
        item.get("evidence_id") for item in evidence_map if item.get("evidence_id")
    }
    cited = set(_extract_valid_evidence_refs(markdown_report, available_ids))
    if isinstance(structured_report, dict):
        cited.update(
            item for item in structured_report.get("evidence_refs", [])
            if item in available_ids
        )
        for block in structured_report.get("visual_blocks", []) or []:
            if isinstance(block, dict):
                cited.update(
                    item for item in block.get("evidence_refs", [])
                    if item in available_ids
                )
        for claim in structured_report.get("claims", []) or []:
            if not isinstance(claim, dict):
                continue
            for relation in claim.get("evidence_relations", []) or []:
                if not isinstance(relation, dict):
                    continue
                evidence_id = relation.get("evidence_id")
                if evidence_id in available_ids:
                    cited.add(evidence_id)
    return [item for item in evidence_map if item.get("evidence_id") in cited]


def _extract_valid_evidence_refs(content: str, available_ids: set[str]) -> List[str]:
    cited = re.findall(r"\[evidence_id:([^\]\s]+)\]", content or "")
    return list(dict.fromkeys(item for item in cited if item in available_ids))


def _build_summary_prompt(
    other_results: List[Dict],
    critic_result: Optional[Dict],
    has_critic: bool,
    user_message: str = "",
    qa_history: Optional[List[Dict]] = None,
    target_units: Optional[int] = None,
    length_policy: Optional[OutputLengthPolicy] = None,
) -> str:
    """构建汇总 prompt

    Args:
        other_results: 非逆向思考顾问的 Agent 结果
        critic_result: 逆向思考顾问结果（如有）
        has_critic: 是否包含逆向思考顾问
        user_message: 用户原始需求
        qa_history: 需求完善阶段的追问回答历史
        target_units: 按任务复杂度计算的正文目标单位数
        length_policy: locale-aware 正文长度策略

    Returns:
        prompt 字符串
    """
    length_policy = length_policy or get_output_length_policy("zh-CN")
    combined_results = list(other_results)
    if critic_result:
        combined_results.append(critic_result)
    if target_units is None:
        target_units = _adaptive_final_report_target_units(
            combined_results,
            length_policy=length_policy,
            user_message=user_message,
            qa_history=qa_history,
        )
    length_requirement = _build_length_requirement(length_policy, target_units)
    summary_opening = (
        "`**One-sentence summary:** ...`"
        if length_policy.locale == "en-US"
        else "`**一句话总结：** ...`"
    )

    # 用户需求区块（原始需求 + 追问回答）
    need_section = ""
    if user_message and user_message.strip():
        need_section = f"\n## 用户原始需求\n\n{user_message.strip()}\n"

    if qa_history:
        qa_text = ""
        for i, qa in enumerate(qa_history, 1):
            if not isinstance(qa, dict):
                # 历史状态里可能混入非 dict 条目（如纯字符串答案），跳过避免崩溃
                qa_text += f"\n**追问 {i}**：\n**用户回答**：{str(qa).strip()}\n"
                continue
            q = str(qa.get("question") or "").strip()
            a = str(qa.get("answer") or "").strip()
            if q or a:
                qa_text += f"\n**追问 {i}**：{q}\n**用户回答**：{a}\n"
        if qa_text:
            need_section += f"\n## 用户补充说明（追问回答）\n{qa_text}\n"

    if has_critic and critic_result:
        # 包含逆向思考顾问的特殊报告结构
        prompt = f"""请综合以下专家的分析结果，针对用户的原始需求，生成一份完整、可直接指导行动的综合报告。
{need_section}
## 重要说明
本次分析包含「逆向思考顾问」的意见，请务必在报告中整合逆向思考的观点，确保报告具有辩证性。

## 报告结构要求

## 面向用户的完整独立最终报告

请把各 Agent 报告仅作为形成判断的内部材料，以单一作者、统一口径写成一份可独立交付的最终分析报告。读者即使没有看过任何 Agent 报告，也应能仅凭本报告理解问题背景、关键判断、依据、建议、风险与下一步。

- 第一行只能是报告标题，不要添加“好的”“以下是”等开场白。
- 标题后的第一个非空段落必须严格写成 {summary_opening}，只用一句话直接回答用户的核心问题并概括最终判断；不要写成“本报告分析了……”之类的元描述，也不要写成发现、建议或风险的条目清单。
- 围绕用户的问题、决策或主题组织正文，不要按 Agent、子任务、工具或证据来源逐份展开。
- 不要设置“各专家关键发现”“Agent 观点汇总”“证据摘录”等来源式拼装章节；除非解释实质分歧或专业边界确有必要，否则正文不提 Agent 姓名和调研过程。
- 将输入中的事实、分析和建议融入连续论证：说明结论是什么、为什么成立、对用户意味着什么，以及应如何行动。不要复制工具输出或证据原文，不要虚构输入中没有的事实。
- 专家意见有分歧时，提炼真正影响结论的分歧，比较依据与适用条件，并给出最终判断；不要只并列呈现不同说法。

{length_requirement}

- 关键事实与判断应给出支撑逻辑与取舍理由，不要机械拉长，也不要只给要点清单。
- 以上目标专门约束 structured response 的 markdown_report 字段；结构化摘要字段不能替代正文。

1. **标题 + 一句话总结**：严格遵守上述开篇格式

2. **直接回应与综合判断**：先回答用户最关心的问题，再说明判断依据、关键条件与取舍；不要泛泛复述需求

3. **主题化深度分析**：按问题本身的逻辑分主题展开，把各专家材料融合进同一条论证链，而不是按来源分组

4. **结论与可执行建议**：给出明确结论、优先级和行动建议，并说明理由、适用条件与预期影响

5. **逆向思考与风险分析**（重要）：
   - 必须单独列出逆向思考顾问的核心质疑
   - 分析这些质疑是否合理
   - 说明如何应对或为何可以忽略这些质疑

6. **实施路径**：按优先级排列具体行动步骤，写清先后关系和必要前提

7. **风险提示与注意事项**

## 结构化图表块要求

在 structured response 的 visual_blocks 中尽量生成可渲染的信息图块：
- 至少包含一个 type="risk_matrix" 的风险矩阵；data.risks 为数组，每项包含 risk、likelihood、impact、mitigation。
- 如果专家意见中存在多个可选方案，增加一个 type="decision_matrix" 的决策矩阵；data.options 为数组，每项包含 option、pros、cons、score、recommendation。
- 只使用文本和结构化数据，不生成图片、base64 或 Markdown 表格作为图表块。

## 专家分析结果

"""
        for result in other_results:
            agent_name = result.get("agent_name", result.get("agent_id"))
            content = _build_agent_summary_input(result)

            if not content or content.strip() == "":
                content = f"（专家 {agent_name} 的分析内容为空）"

            prompt += f"### {agent_name}\n{content}\n\n"

        # 单独添加逆向思考顾问的结果
        if critic_result:
            critic_name = critic_result.get("agent_name", "逆向思考顾问")
            critic_content = _build_agent_summary_input(
                critic_result,
                fallback_limit=_SUMMARY_CRITIC_CONTENT_CHAR_LIMIT,
            )

            if not critic_content or critic_content.strip() == "":
                critic_content = "（逆向思考顾问的分析内容为空）"

            prompt += f"""---

## 逆向思考顾问意见

### {critic_name}
{critic_content}

---

**请在生成报告时，特别关注以上逆向思考意见，并在"逆向思考与风险分析"章节中予以回应。**
"""
    else:
        # 普通报告结构
        prompt = f"""请综合以下专家的分析结果，针对用户的原始需求，生成一份完整、可直接指导行动的综合报告。
{need_section}
## 报告结构要求

## 面向用户的完整独立最终报告

请把各 Agent 报告仅作为形成判断的内部材料，以单一作者、统一口径写成一份可独立交付的最终分析报告。读者即使没有看过任何 Agent 报告，也应能仅凭本报告理解问题背景、关键判断、依据、建议、风险与下一步。

- 第一行只能是报告标题，不要添加“好的”“以下是”等开场白。
- 标题后的第一个非空段落必须严格写成 {summary_opening}，只用一句话直接回答用户的核心问题并概括最终判断；不要写成“本报告分析了……”之类的元描述，也不要写成发现、建议或风险的条目清单。
- 围绕用户的问题、决策或主题组织正文，不要按 Agent、子任务、工具或证据来源逐份展开。
- 不要设置“各专家关键发现”“Agent 观点汇总”“证据摘录”等来源式拼装章节；除非解释实质分歧或专业边界确有必要，否则正文不提 Agent 姓名和调研过程。
- 将输入中的事实、分析和建议融入连续论证：说明结论是什么、为什么成立、对用户意味着什么，以及应如何行动。不要复制工具输出或证据原文，不要虚构输入中没有的事实。
- 专家意见有分歧时，提炼真正影响结论的分歧，比较依据与适用条件，并给出最终判断；不要只并列呈现不同说法。

{length_requirement}

- 关键事实与判断应给出支撑逻辑与取舍理由，不要机械拉长，也不要只给要点清单。
- 以上目标专门约束 structured response 的 markdown_report 字段；结构化摘要字段不能替代正文。

1. **标题 + 一句话总结**：严格遵守上述开篇格式

2. **直接回应与综合判断**：先回答用户最关心的问题，再说明判断依据、关键条件与取舍；不要泛泛复述需求

3. **主题化深度分析**：按问题本身的逻辑分主题展开，把各专家材料融合进同一条论证链，而不是按来源分组

4. **结论与可执行建议**：给出明确结论、优先级和行动建议，并说明理由、适用条件与预期影响

5. **实施路径**：按优先级排列具体行动步骤，写清先后关系和必要前提

6. **风险提示与注意事项**

## 结构化图表块要求

在 structured response 的 visual_blocks 中尽量生成可渲染的信息图块：
- 至少包含一个 type="risk_matrix" 的风险矩阵；data.risks 为数组，每项包含 risk、likelihood、impact、mitigation。
- 如果专家意见中存在多个可选方案，增加一个 type="decision_matrix" 的决策矩阵；data.options 为数组，每项包含 option、pros、cons、score、recommendation。
- 只使用文本和结构化数据，不生成图片、base64 或 Markdown 表格作为图表块。

## 专家分析结果

"""
        for result in other_results:
            agent_name = result.get("agent_name", result.get("agent_id"))
            content = _build_agent_summary_input(result)

            if not content or content.strip() == "":
                content = f"（专家 {agent_name} 的分析内容为空）"

            prompt += f"### {agent_name}\n{content}\n\n"

    return prompt


def _build_agent_summary_input(
    result: Dict[str, Any],
    fallback_limit: int = _SUMMARY_AGENT_CONTENT_CHAR_LIMIT,
) -> str:
    """构建单个 Agent 报告用于最终综合的输入片段。

    最终报告是独立综合分析，因此只消费每个 Agent 自身的综合报告
    （结构化摘要 + 报告正文），不再注入证据摘录或原始报告摘录。
    """
    summary = _extract_agent_summary(result)
    lines: List[str] = []
    if summary:
        lines = ["Agent 内部分析摘要（仅供形成最终判断）："]
        _append_summary_line(lines, "一句话结论", summary.get("one_sentence"))
        _append_summary_items(lines, "关键发现", summary.get("key_findings"))
        _append_summary_items(lines, "建议", summary.get("recommendations"))
        _append_summary_items(lines, "风险", summary.get("risks"))
        _append_summary_items(lines, "待确认问题", summary.get("open_questions"))
        confidence = summary.get("confidence")
        if confidence is not None:
            lines.append(f"- 置信度：{confidence}")

    if result.get("quality_status") == "degraded":
        reason = str(result.get("degradation_reason") or "Agent 执行发生降级").strip()
        lines.append(f"- 质量状态：降级（{reason}）")

    content = result.get("content") or result.get("output", "")
    body = _limit_summary_content(content, fallback_limit)

    if lines:
        text = "\n".join(lines)
        if body and body.strip():
            text += "\n\nAgent 综合报告正文（仅供形成最终判断，不按来源复述）：\n" + body.strip()
        return text

    return body.strip() if body and body.strip() else "（该 Agent 无分析内容）"


def _extract_agent_summary(result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Return the first usable Agent summary from result payloads."""
    direct_summary = result.get("summary")
    if _is_usable_summary(direct_summary):
        return direct_summary

    structured_report = result.get("structured_report") or {}
    if isinstance(structured_report, dict):
        structured_summary = structured_report.get("summary")
        if _is_usable_summary(structured_summary):
            return structured_summary

    return None


def _is_usable_summary(summary: Any) -> bool:
    if not isinstance(summary, dict):
        return False
    # 置信度过低时视为不可用，回退全文裁剪（roadmap §4.5 约束）
    confidence = summary.get("confidence")
    if isinstance(confidence, (int, float)) and confidence < _SUMMARY_CONFIDENCE_THRESHOLD:
        return False
    fields = (
        "one_sentence",
        "key_findings",
        "recommendations",
        "risks",
        "open_questions",
        "evidence_refs",
    )
    for field in fields:
        value = summary.get(field)
        if isinstance(value, str) and value.strip():
            return True
        if isinstance(value, list) and _normalize_summary_items(value):
            return True
    return False


def _append_summary_line(lines: List[str], label: str, value: Any) -> None:
    if isinstance(value, str) and value.strip():
        lines.append(f"- {label}：{value.strip()}")


def _append_summary_items(lines: List[str], label: str, value: Any) -> None:
    if not isinstance(value, list):
        return
    items = _normalize_summary_items(value)
    if not items:
        return
    clipped = items[:_SUMMARY_LIST_ITEM_LIMIT]
    lines.append(f"- {label}：" + "；".join(clipped))
    if len(items) > _SUMMARY_LIST_ITEM_LIMIT:
        lines.append(f"  （{label}已截断至 {_SUMMARY_LIST_ITEM_LIMIT} 条）")


def _normalize_summary_items(value: List[Any]) -> List[str]:
    items: List[str] = []
    for item in value:
        if item is None:
            continue
        text = str(item).strip()
        if text:
            items.append(text)
    return items


def _call_llm_for_summary(
    prompt: str,
    target_units: Optional[int] = None,
    length_policy: Optional[OutputLengthPolicy] = None,
    available_evidence_ids: Optional[set[str]] = None,
) -> tuple[str, Optional[dict], Optional[dict]]:
    """调用 LLM 生成汇总报告

    Args:
        prompt: 汇总 prompt

    Returns:
        汇总报告（Markdown 格式）
    """
    svc = get_services()
    if svc.llm_service is None:
        raise ValueError("LLM service not initialized")

    length_policy = length_policy or get_output_length_policy("zh-CN")
    max_tokens = _get_final_report_max_tokens(
        svc.llm_service,
        target_units=target_units,
        length_policy=length_policy,
    )

    from .node_utils import build_current_date_prompt
    system_content = (
        (
            "You are the sole author of a self-contained final analysis report. Integrate multiple domain "
            "experts' materials into one coherent judgment organized around the user's question, not around "
            "the sources. Start with a title followed immediately by a one-sentence summary, then provide "
            "the reasoning and actions needed to make the report independently useful."
            if length_policy.locale == "en-US"
            else
            "你是一份完整独立最终分析报告的唯一作者。请把多个领域专家的材料内化为统一判断，"
            "围绕用户问题而非材料来源组织报告。第一行写标题，随后立即用一句话总结直接回答核心问题，"
            "再展开足以让报告独立成立的分析依据、取舍和行动建议；不要拼装或转述各 Agent 报告。"
        )
        + build_current_date_prompt()
        + build_output_locale_instruction(length_policy.locale, "final_report")
    )
    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": prompt},
    ]
    try:
        structured_model = safe_async_run(
            svc.llm_service.call_structured(
                messages=messages,
                response_model=FinalReportResult,
                max_tokens=max_tokens,
                max_retries=1,
                timeout=_FINAL_REPORT_TIMEOUT_SECONDS,
            )
        )
    except Exception as e:
        logger.warning("Structured summary failed, falling back to markdown call: %s", _short_error(e))
    else:
        quality_issues = _final_report_quality_issues(
            structured_model.markdown_report,
            prompt=prompt,
            target_units=target_units,
            length_policy=length_policy,
        )
        if quality_issues:
            logger.warning(
                "Structured final report has quality warnings: %s",
                "; ".join(quality_issues),
            )

        structured_payload = final_report_structured_payload(structured_model) or {}
        for index, claim in enumerate(structured_payload.get("claims", []) or [], 1):
            if isinstance(claim, dict):
                claim["claim_id"] = f"final_claim_{index}"
        if available_evidence_ids is not None:
            valid_refs = _extract_valid_evidence_refs(
                structured_model.markdown_report,
                available_evidence_ids,
            )
            valid_refs.extend(
                item for item in structured_payload.get("evidence_refs", [])
                if item in available_evidence_ids and item not in valid_refs
            )
            structured_payload["evidence_refs"] = valid_refs
            for block in structured_payload.get("visual_blocks", []) or []:
                if isinstance(block, dict):
                    block["evidence_refs"] = [
                        item for item in block.get("evidence_refs", [])
                        if item in available_evidence_ids
                    ]
        structured_payload["quality_status"] = "warning" if quality_issues else "normal"
        structured_payload["quality_warnings"] = quality_issues
        return (
            structured_model.markdown_report,
            final_report_summary_payload(structured_model),
            structured_payload,
        )

    # 调用 LLM（同步模式，用于长输出场景）
    # call_sync 直接返回字符串，无需解析 Anthropic SDK 格式
    if length_policy.locale == "en-US":
        markdown_constraints = """

## Markdown fallback output constraints

Return only one complete Markdown final report.
Do not append structured fields such as title, executive_summary, key_findings, recommendations, risks, or next_steps after the report body.
Do not repeat the Agent input materials as an appendix or trailing summary.
"""
    else:
        markdown_constraints = """

## Markdown fallback 输出约束

本次调用只需要输出一份完整 Markdown 最终报告正文。
不要在报告正文之后追加 title、executive_summary、key_findings、recommendations、risks、next_steps 等结构化摘要字段。
不要把输入中的 Agent 内部分析材料作为附录或尾部摘要复述。
"""
    markdown_prompt = prompt + markdown_constraints
    try:
        response_text = svc.llm_service.call_sync(
            message=markdown_prompt,
            system_prompt=system_content,
            max_tokens=max_tokens,
            max_attempts=1,
            timeout=_FINAL_REPORT_TIMEOUT_SECONDS,
            reject_truncated=True,
        )
    except Exception as e:
        logger.warning("Markdown summary failed, using local fallback: %s", _short_error(e))
        fallback_heading = (
            "## Final Recommendation\n\nFinal report generation timed out. The expert conclusions available so far are summarized below:\n\n"
            if length_policy.locale == "en-US"
            else "## 综合建议\n\n最终报告生成超时，以下为专家结论摘要：\n\n"
        )
        return (
            fallback_heading + _fallback_summary_from_prompt(prompt),
            None,
            None,
        )

    return response_text, None, None


def _final_report_quality_issues(
    report: str,
    prompt: str = "",
    target_units: Optional[int] = None,
    length_policy: Optional[OutputLengthPolicy] = None,
) -> List[str]:
    """Return quality guard failures for structured final report markdown."""
    length_policy = length_policy or get_output_length_policy("zh-CN")
    text = (report or "").strip()
    actual_units = length_policy.count_units(text)
    required_units = _final_report_required_units(target_units, length_policy)
    headings = re.findall(r"(?m)^#{1,6}\s+\S+", text)

    issues: List[str] = []
    if actual_units < required_units:
        issues.append(
            f"{length_policy.unit}={actual_units} < {required_units}"
        )
    if len(headings) < _FINAL_REPORT_MIN_HEADINGS:
        issues.append(f"headings={len(headings)} < {_FINAL_REPORT_MIN_HEADINGS}")
    return issues


def _final_report_required_units(
    target_units: Optional[int],
    length_policy: OutputLengthPolicy,
) -> int:
    """Return the locale-aware adaptive minimum for the final report quality gate."""
    target_units = target_units or length_policy.minimum_units
    return min(
        length_policy.maximum_units,
        max(length_policy.minimum_units, int(target_units * 0.6)),
    )


def _get_final_report_max_tokens(
    llm_service: Any,
    target_units: Optional[int] = None,
    length_policy: Optional[OutputLengthPolicy] = None,
) -> int:
    """获取最终综合报告的输出预算。"""
    length_policy = length_policy or get_output_length_policy("zh-CN")
    model_max_tokens = llm_service.get_max_output_tokens()
    target_units = target_units or length_policy.maximum_units
    adaptive_budget = length_policy.output_token_budget(target_units)
    report_max_tokens = min(model_max_tokens, _FINAL_REPORT_MAX_TOKENS, adaptive_budget)
    if report_max_tokens < model_max_tokens:
        logger.info(
            "Final report synthesis: capping max_tokens from %s to %s",
            model_max_tokens,
            report_max_tokens,
        )
    return report_max_tokens


def _fit_target_units_to_output_budget(
    target_units: int,
    length_policy: OutputLengthPolicy,
    llm_service: Any,
) -> int:
    """Keep the requested report length inside the model's real completion budget."""
    output_tokens = min(llm_service.get_max_output_tokens(), _FINAL_REPORT_MAX_TOKENS)
    body_token_budget = max(256, output_tokens - 1024)
    safe_units = max(256, int(body_token_budget / length_policy.tokens_per_unit))
    fitted = min(target_units, safe_units)
    if fitted < target_units:
        logger.info(
            "Final report synthesis: fitting target %s -> %s %s for model output budget %s",
            target_units,
            fitted,
            length_policy.unit,
            output_tokens,
        )
    return fitted


def _limit_summary_content(content: str, limit: int = _SUMMARY_AGENT_CONTENT_CHAR_LIMIT) -> str:
    """限制单个专家结果进入最终汇总 prompt 的长度。"""
    if not content:
        return content
    if len(content) <= limit:
        return content
    return content[:limit] + f"\n...(内容过长，已截断至 {limit} 字符)"


def _short_error(error: Exception) -> str:
    """避免 instructor/httpx 超时把完整 XML/traceback 打进业务日志。"""
    text = str(error).strip()
    if not text:
        return error.__class__.__name__
    text = " ".join(text.split())
    if "Request timed out" in text:
        return "Request timed out."
    return text[:300]


def _fallback_summary_from_prompt(prompt: str) -> str:
    """LLM 汇总不可用时，从已裁剪 prompt 中提取专家摘要片段。"""
    marker = "## 专家分析结果"
    if marker not in prompt:
        return prompt[:12000]
    text = prompt.split(marker, 1)[1].strip()
    return text[:12000] + ("\n...(已截断)" if len(text) > 12000 else "")


def _fallback_summary(
    other_results: List[Dict],
    critic_result: Optional[Dict],
    has_critic: bool,
    locale: str = "zh-CN",
) -> str:
    """降级汇总方案（LLM 服务不可用时）

    Args:
        other_results: 非逆向思考顾问的 Agent 结果
        critic_result: 逆向思考顾问结果（如有）
        has_critic: 是否包含逆向思考顾问

    Returns:
        简化汇总报告
    """
    is_english = locale == "en-US"
    report = (
        "## Final Recommendation\n\nA concise summary of the expert findings follows:\n\n"
        if is_english
        else "## 综合建议\n\n以下为各专家意见的简要汇总：\n\n"
    )

    for result in other_results:
        agent_name = result.get("agent_name", result.get("agent_id"))
        content = result.get("content", "")
        # 截取前 20000 字符
        summary = content[:20000] + "..." if len(content) > 20000 else content
        report += f"### {agent_name}\n{summary}\n\n"

    if has_critic and critic_result:
        critic_name = critic_result.get(
            "agent_name",
            "Critical Thinking Advisor" if is_english else "逆向思考顾问",
        )
        critic_content = critic_result.get("content", "")[:20000]
        critic_label = "Critical Review" if is_english else "逆向思考"
        report += f"### {critic_name} ({critic_label})\n{critic_content}...\n\n"

    return report


def _build_length_requirement(length_policy: OutputLengthPolicy, target_units: int) -> str:
    if length_policy.locale == "en-US":
        return (
            f"- Target approximately {target_units} effective words in the report body. Keep narrow questions "
            "focused and develop complex questions fully without repetition added only for length."
        )
    return (
        f"- 本次正文目标有效字符数约 {target_units}；窄问题应聚焦，复杂问题应充分展开，"
        "不要为凑篇幅重复内容。"
    )


def _final_report_visible_text(
    report: str,
    summary: Optional[dict],
    structured_report: Optional[dict] = None,
) -> str:
    """Collect report, summary, and visual-block text without machine identifiers."""
    values = [report or ""]

    def collect(value: Any, *, key: str = "") -> None:
        normalized_key = key.casefold()
        if (
            normalized_key in {
                "block_id",
                "type",
                "evidence_refs",
                "source_quality_status",
                "source_degradation_reasons",
                "quality_status",
                "quality_warnings",
            }
            or normalized_key == "id"
            or normalized_key.endswith("_id")
        ):
            return
        if isinstance(value, str):
            values.append(value)
        elif isinstance(value, dict):
            for item_key, item in value.items():
                collect(item, key=str(item_key))
        elif isinstance(value, list):
            for item in value:
                collect(item)

    collect(summary or {})
    for block in (structured_report or {}).get("visual_blocks", []) or []:
        if not isinstance(block, dict):
            continue
        collect(block.get("title"), key="title")
        collect(block.get("data"), key="data")
    return "\n".join(values)
