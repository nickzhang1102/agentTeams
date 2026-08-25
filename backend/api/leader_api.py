"""
Leader Agent API Router
提供 Leader 会话的 RESTful API 端点

SSE 端点已迁移到 FastAPI StreamingResponse。
"""
import logging
import math
from datetime import datetime
from typing import Optional, List, Dict, AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from api.deps import get_current_user
from models import (
    Conversation, Message, File, LeaderSession,
    LeaderAgentResult, LeaderFinalReport, User
)
from services.llm_service import LLMConfigurationError, resolve_model_info
from services.file_storage import FileStorage
from services.decision_run_service import DecisionRunService
from utils.sse_async import create_sse_streaming_response
from utils.error_handler import safe_error_response, safe_sse_error
from utils.time_utils import utcnow_naive
from config import Config

# LangGraph 异步入口（FastAPI SSE）
from leader.langgraph_entry import async_run_leader_workflow
from leader.leader_persistence import (
    create_leader_session,
    mark_session_failed,
    mark_session_stopped,
)
from leader.locale_generation import resolve_generation_locale
from leader.question_answers import create_question_answer_events
from context.context_builder import ContextBuilder

# 心跳配置
HEARTBEAT_INTERVAL = 30
LEADER_SSE_MAX_DURATION = Config.LEADER_SSE_MAX_DURATION
STALE_SESSION_TIMEOUT_MINUTES = Config.STALE_SESSION_TIMEOUT_MINUTES
STALE_SESSION_GRACE_SECONDS = Config.STALE_SESSION_GRACE_SECONDS

# 配置日志
logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api/leader", tags=["leader"])


def _effective_stale_session_timeout_minutes() -> int:
    workflow_minutes = math.ceil(
        (LEADER_SSE_MAX_DURATION + STALE_SESSION_GRACE_SECONDS) / 60
    )
    return max(STALE_SESSION_TIMEOUT_MINUTES, workflow_minutes)


# ==================== Pydantic Models ====================

class StartLeaderRequest(BaseModel):
    """启动 Leader 会话请求"""
    conversation_id: int = Field(..., gt=0)
    message: str = Field(..., min_length=1)
    file_ids: Optional[List[int]] = Field(default_factory=list)
    skip_to_execution: bool = False
    pre_selected_agents: Optional[List[str]] = Field(default=None, max_length=10)
    assessment_threshold: int = Field(default=60, ge=0, le=100)
    system_prompt_addition: Optional[str] = Field(default=None, max_length=2000)
    locale: Optional[str] = None


class AnswerQuestionsRequest(BaseModel):
    """回答问题请求"""
    session_id: int = Field(..., gt=0)
    answers: List[str] = Field(..., min_length=1)


class StopExecutionRequest(BaseModel):
    """停止执行请求"""
    session_id: int = Field(..., description="Session ID")


# ==================== Helper Functions ====================

def build_llm_config(
    override_max_tokens: Optional[int] = None,
    model_info: Optional[Dict] = None,
) -> dict:
    """构建 LLM 配置字典（消除 4 处重复代码）

    Args:
        override_max_tokens: 覆盖默认的 max_tokens（如从 LLMService 获取的模型感知值）
        model_info: 从 DB 读取的模型配置；为空时解析数据库默认模型

    Returns:
        dict: 完整的 LLM 配置
    """
    resolved = model_info or resolve_model_info()

    return {
        'LLM_API_KEY': resolved['api_key'],
        'LLM_BASE_URL': resolved['base_url'],
        'LLM_MODEL': resolved['model_id'],
        'LLM_MAX_TOKENS': override_max_tokens or resolved['max_output_tokens'],
        'AGENTS_DIR': Config.AGENTS_DIR or '',
        'WORKSPACE_DIR': Config.WORKSPACE_DIR or '',
        'OPENHARNESS_ENABLED': Config.OPENHARNESS_ENABLED if hasattr(Config, 'OPENHARNESS_ENABLED') else True,
        'MAX_AGENT_PARALLEL': 5,
    }


def _agent_result_to_dict(
    agent_result: LeaderAgentResult,
    *,
    include_private_evidence: bool = False,
    public_access: bool = False,
) -> dict:
    """Serialize an Agent result with an explicit private-evidence boundary."""
    payload = agent_result.to_dict()
    if include_private_evidence:
        return payload

    payload.pop("raw_tool_results", None)
    evidence_map = payload.get("evidence_map")
    if isinstance(evidence_map, list):
        payload["evidence_map"] = [
            _evidence_summary_to_dict(item, public_access=public_access)
            if isinstance(item, dict)
            else item
            for item in evidence_map
        ]
    return payload


def _evidence_summary_to_dict(item: dict, *, public_access: bool) -> dict:
    """Remove private lookup fields from list/share evidence projections."""
    payload = {key: value for key, value in item.items() if key != "raw_ref"}
    if not public_access:
        return payload
    if payload.get("source_type") != "web":
        payload.pop("source_id", None)
        payload.pop("locator", None)
        payload.pop("url", None)
    return payload


def _final_report_to_dict(
    final_report: Optional[LeaderFinalReport],
    *,
    public_access: bool = False,
) -> dict | str:
    """序列化最终报告；无报告时保持旧空字符串契约。"""
    if not final_report:
        return ''
    payload = final_report.to_dict()
    evidence_map = payload.get("evidence_map")
    if isinstance(evidence_map, list):
        payload["evidence_map"] = [
            _evidence_summary_to_dict(item, public_access=public_access)
            if isinstance(item, dict)
            else item
            for item in evidence_map
        ]
    return payload


def _build_leader_messages_and_sessions(
    conversation_id: int,
    db_session: Session,
    current_user_id: Optional[int] = None
) -> dict:
    """
    构建 Leader 会话响应数据（公共逻辑）

    查询该对话的所有 LeaderSession 及关联消息，返回统一结构。
    无 Leader 会话时返回空数据。

    Args:
        conversation_id: 对话 ID
        db_session: 数据库会话（依赖注入）

    Returns:
        {'success': True, 'sessions': [...], 'messages': [...]}
    """
    leader_sessions = db_session.query(LeaderSession).filter_by(
        conversation_id=conversation_id
    ).order_by(LeaderSession.started_at.asc()).all()

    if not leader_sessions:
        return {'success': True, 'sessions': [], 'messages': []}

    session_ids = [s.id for s in leader_sessions]

    # 批量获取 Leader 内部消息（PERF-03: 替代逐会话查询）
    messages = db_session.query(Message).filter(
        Message.leader_session_id.in_(session_ids),
        Message.sequence_number.isnot(None)
    ).order_by(Message.leader_session_id, Message.sequence_number).all()

    # 批量获取 Agent 结果（PERF-03: 替代 N 次逐会话查询）
    all_agent_results = db_session.query(LeaderAgentResult).filter(
        LeaderAgentResult.leader_session_id.in_(session_ids)
    ).order_by(LeaderAgentResult.leader_session_id, LeaderAgentResult.sequence_number).all()

    # 批量获取最终报告（PERF-03: 替代 N 次逐会话查询）
    all_final_reports = db_session.query(LeaderFinalReport).filter(
        LeaderFinalReport.leader_session_id.in_(session_ids)
    ).all()

    # 按 session_id 分组，构建查找表
    from collections import defaultdict
    messages_by_session: Dict[int, list] = defaultdict(list)
    for msg in messages:
        messages_by_session[msg.leader_session_id].append(msg)

    agent_results_by_session: Dict[int, list] = defaultdict(list)
    for ar in all_agent_results:
        agent_results_by_session[ar.leader_session_id].append(ar)

    reports_by_session: Dict[int, LeaderFinalReport] = {}
    for r in all_final_reports:
        reports_by_session[r.leader_session_id] = r

    # 构建通用消息列表（过滤掉 normal/agent_result/final_report/summary）
    messages_list = []
    for msg in messages:
        if msg.role in ('user', 'assistant') and msg.message_type == 'normal':
            continue
        if msg.message_type in ['agent_result', 'final_report', 'summary']:
            continue
        messages_list.append({
            'id': msg.id,
            'type': msg.message_type,
            'content': msg.content,
            'content_locale': msg.content_locale,
            'sequence_number': msg.sequence_number,
            'created_at': msg.created_at.isoformat() + 'Z' if msg.created_at else None,
            'leader_session_id': msg.leader_session_id
        })

    sessions_data = []
    run_service = DecisionRunService(db_session)
    public_access = current_user_id is None
    for ls in leader_sessions:
        total_time = 0
        if ls.completed_at and ls.started_at:
            total_time = (ls.completed_at - ls.started_at).total_seconds()

        # 从预取数据构建会话详情
        sid = ls.id
        assessment_details = {}
        team_config = {}
        for msg in messages_by_session.get(sid, []):
            if msg.message_type == 'assessment':
                assessment_details = msg.content
            elif msg.message_type == 'team_config':
                team_config = msg.content

        final_report_record = reports_by_session.get(sid)
        agent_results_list = agent_results_by_session.get(sid, [])

        sessions_data.append({
            'id': ls.id,
            'state': ls.state,
            'decision_run': run_service.projection_for_session(ls),
            'assessment_score': ls.assessment_score,
            'risk_level': ls.risk_level,
            'selected_agents': ls.get_selected_agents_list(),
            'assessment_details': assessment_details,
            'team_config': team_config,
            'agent_results': [
                _agent_result_to_dict(
                    ar,
                    include_private_evidence=False,
                    public_access=public_access,
                )
                for ar in agent_results_list
            ],
            'final_report': _final_report_to_dict(
                final_report_record,
                public_access=public_access,
            ),
            'started_at': ls.started_at.isoformat() + 'Z' if ls.started_at else None,
            'completed_at': ls.completed_at.isoformat() + 'Z' if ls.completed_at else None,
            'total_time': total_time,
            'user_message': ls.user_message
        })

    return {'success': True, 'sessions': sessions_data, 'messages': messages_list}


def get_session_data_from_messages(
    session_id: int,
    db_session: Session,
    current_user_id: Optional[int] = None
) -> dict:
    """从新表结构获取会话数据"""
    # 获取 Leader 流程消息
    messages = db_session.query(Message).filter(
        Message.leader_session_id == session_id,
        Message.sequence_number.isnot(None)
    ).order_by(Message.sequence_number).all()

    # 获取 Agent 结果
    agent_results = db_session.query(LeaderAgentResult).filter_by(
        leader_session_id=session_id
    ).order_by(LeaderAgentResult.sequence_number).all()

    # 获取最终报告
    final_report_record = db_session.query(LeaderFinalReport).filter_by(
        leader_session_id=session_id
    ).first()

    # 构建数据结构
    data = {
        'assessment_details': {},
        'team_config': {},
        'agent_results': [
            _agent_result_to_dict(
                agent_result,
                include_private_evidence=False,
            )
            for agent_result in agent_results
        ],
        'final_report': _final_report_to_dict(final_report_record)
    }
    leader_session = db_session.get(LeaderSession, session_id)
    data['decision_run'] = (
        DecisionRunService(db_session).projection_for_session(leader_session)
        if leader_session is not None
        else None
    )

    # 按消息类型提取普通消息数据
    for msg in messages:
        if msg.message_type == 'assessment':
            data['assessment_details'] = msg.content
        elif msg.message_type == 'team_config':
            data['team_config'] = msg.content

    return data


def _resolve_model_or_http_error(model_id: Optional[str], db_session: Session) -> Dict:
    """Resolve a usable DB-backed model before creating workflow side effects."""
    try:
        return resolve_model_info(model_id, db_session=db_session)
    except LLMConfigurationError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                'code': 'LLM_NOT_CONFIGURED',
                'error': str(exc),
            },
        ) from exc


# ==================== Non-SSE Endpoints ====================

@router.get('/session/{conversation_id}')
def get_leader_session(
    conversation_id: int,
    user: User = Depends(get_current_user),
    db_session: Session = Depends(get_db),
):
    """获取 Leader 会话完整数据（需认证）"""
    try:
        conversation = db_session.get(Conversation, conversation_id)
        if not conversation or conversation.user_id != user.id:
            raise HTTPException(
                status_code=404,
                detail={'success': False, 'error': '对话不存在或无权访问'}
            )

        result = _build_leader_messages_and_sessions(
            conversation_id,
            db_session=db_session,
            current_user_id=user.id
        )
        if not result['sessions']:
            raise HTTPException(
                status_code=404,
                detail={'success': False, 'error': '未找到 Leader 会话'}
            )
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get leader session failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={'success': False, **safe_error_response(e, "获取 Leader 会话失败")}
        )


@router.post('/stop')
def stop_execution(
    request: StopExecutionRequest,
    user: User = Depends(get_current_user),
    db_session: Session = Depends(get_db),
):
    """
    停止 Leader 执行

    请求体:
        {
            "session_id": int
        }

    返回:
        {
            "success": bool,
            "message": str
        }
    """
    try:
        user_id = user.id

        # 查询 session
        session = db_session.get(LeaderSession, request.session_id)
        if not session:
            raise HTTPException(
                status_code=404,
                detail={'error': 'Session 不存在'}
            )

        # 验证归属
        conversation = db_session.get(Conversation, session.conversation_id)
        if not conversation or conversation.user_id != user_id:
            raise HTTPException(
                status_code=403,
                detail={'error': '无权访问此 session'}
            )

        mark_session_stopped(db_session, session.id)

        return {
            'success': True,
            'message': '已发送停止请求'
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Stop execution failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=safe_error_response(e, "停止执行失败")
        )


@router.get('/session/share/{share_token}')
def get_leader_session_by_share_token(
    share_token: str,
    request: Request,
    db_session: Session = Depends(get_db),
):
    """通过分享令牌公开访问 Leader 会话数据（无需认证，但记录访问日志）"""
    try:
        # 访问审计日志
        client_ip = request.client.host if request.client else "unknown"
        logger.info(f"Leader share access: token={share_token[:8]}..., ip={client_ip}")

        conversation = db_session.query(Conversation).filter_by(share_token=share_token).first()
        if not conversation:
            raise HTTPException(
                status_code=404,
                detail={'success': False, 'error': '对话不存在或链接已失效'}
            )

        return _build_leader_messages_and_sessions(conversation.id, db_session=db_session)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get leader session by share token failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={'success': False, **safe_error_response(e, "获取分享会话失败")}
        )


@router.get('/status/{session_id}')
def get_leader_status(
    session_id: int,
    include_results: bool = Query(False, description="是否返回完整 Agent 结果和最终报告"),
    user: User = Depends(get_current_user),
    db_session: Session = Depends(get_db),
):
    """
    查询 Leader 会话状态

    返回:
        {
            "session_id": int,
            "state": str,
            "assessment_score": int,
            "selected_agents": list,
            "final_report": str,
            "started_at": str,
            "completed_at": str
        }
    """
    try:
        user_id = user.id

        # 查询 session
        session = db_session.get(LeaderSession, session_id)
        if not session:
            raise HTTPException(
                status_code=404,
                detail={'error': 'Session 不存在'}
            )

        # 验证归属
        conversation = db_session.get(Conversation, session.conversation_id)
        if not conversation or conversation.user_id != user_id:
            raise HTTPException(
                status_code=403,
                detail={'error': '无权访问此 session'}
            )

        terminal_states = {'completed', 'stopped', 'failed'}
        response = {
            'session_id': session.id,
            'locale': session.locale,
            'state': session.state,
            'is_running': session.state not in terminal_states,
            'assessment_score': session.assessment_score,
            'risk_level': session.risk_level,
            'selected_agents': session.get_selected_agents_list(),
            'started_at': session.started_at.isoformat() + 'Z' if session.started_at else None,
            'completed_at': session.completed_at.isoformat() + 'Z' if session.completed_at else None,
            'total_time': (session.completed_at - session.started_at).total_seconds() if session.completed_at and session.started_at else None,
            'error_message': session.error_message,
            'decision_run': DecisionRunService(db_session).projection_for_session(session),
        }

        if include_results:
            agent_results = db_session.query(LeaderAgentResult).filter_by(
                leader_session_id=session_id
            ).order_by(LeaderAgentResult.sequence_number.asc()).all()

            final_report_record = db_session.query(LeaderFinalReport).filter_by(
                leader_session_id=session_id
            ).first()

            response['agent_results'] = [
                _agent_result_to_dict(r, include_private_evidence=False)
                for r in agent_results
            ]
            response['final_report'] = _final_report_to_dict(final_report_record)

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get leader status failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=safe_error_response(e, "查询状态失败")
        )


# ==================== SSE Endpoints (FastAPI StreamingResponse) ====================

@router.post('/start')
async def start_leader_session(
    body: StartLeaderRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db_session: Session = Depends(get_db),
) -> StreamingResponse:
    """启动 Leader 会话（SSE 流式响应）"""
    return await _start_leader_workflow(
        conversation_id=body.conversation_id,
        message=body.message,
        file_ids=body.file_ids or [],
        user=user,
        db_session=db_session,
        skip_to_execution=body.skip_to_execution,
        pre_selected_agents=body.pre_selected_agents,
        assessment_threshold=body.assessment_threshold,
        system_prompt_addition=body.system_prompt_addition,
        explicit_locale=body.locale,
        accept_language=request.headers.get('accept-language'),
    )


async def _start_leader_workflow(
    conversation_id: int,
    message: str,
    file_ids: List[int],
    user: User,
    db_session: Session,
    skip_to_execution: bool = False,
    pre_selected_agents: Optional[List[str]] = None,
    assessment_threshold: int = 60,
    system_prompt_addition: Optional[str] = None,
    explicit_locale: Optional[str] = None,
    accept_language: Optional[str] = None,
) -> StreamingResponse:
    """公共 Leader 启动逻辑（start 端点和 template apply 共用）"""
    user_id = user.id

    # === 1. 验证对话归属 ===
    conversation = db_session.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.user_id == user_id,
    ).with_for_update().first()
    if not conversation:
        raise HTTPException(status_code=404, detail={'error': '对话不存在或无权访问'})

    try:
        generation_locale = resolve_generation_locale(
            explicit_locale=explicit_locale,
            conversation_locale=conversation.default_locale,
            preferred_locale=user.preferred_locale,
            accept_language=accept_language,
        )
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail={'code': 'UNSUPPORTED_LOCALE', 'error': '不支持的语言'},
        )

    # === 2. 验证文件归属 ===
    uploaded_files = []
    file_names = []
    if file_ids:
        for file_id in file_ids:
            file_record = db_session.get(File, file_id)
            if not file_record:
                raise HTTPException(status_code=404, detail={'error': f'文件ID {file_id} 不存在'})
            if file_record.user_id != user_id:
                raise HTTPException(status_code=403, detail={'error': f'无权访问文件ID {file_id}'})
            if file_record.conversation_id is not None and file_record.conversation_id != conversation_id:
                raise HTTPException(status_code=403, detail={'error': f'文件ID {file_id} 不属于此对话'})
            uploaded_files.append(file_record)
            file_names.append(file_record.filename)

    # === 2.5 快速模式参数校验 ===
    if skip_to_execution:
        if not pre_selected_agents:
            raise HTTPException(
                status_code=400,
                detail={'error': '快速模式必须指定至少一个 Agent'}
            )
        from models import AgentConfig
        agent_ids = pre_selected_agents
        if len(agent_ids) != len(set(agent_ids)):
            raise HTTPException(
                status_code=400,
                detail={'error': '快速模式不能重复指定同一个 Agent'}
            )
        configs = {
            c.agent_id: c
            for c in db_session.query(AgentConfig).filter(AgentConfig.agent_id.in_(agent_ids)).all()
        }
        for agent_id in agent_ids:
            config = configs.get(agent_id)
            if not config:
                raise HTTPException(
                    status_code=400,
                    detail={'error': f"Agent '{agent_id}' 不存在"}
                )
            if not config.is_enabled:
                raise HTTPException(
                    status_code=400,
                    detail={'error': f"Agent '{agent_id}' 已禁用"}
                )

    # === 2.6 在任何持久化副作用前验证模型 ===
    model_info = _resolve_model_or_http_error(
        conversation.model_override,
        db_session,
    )
    if explicit_locale is not None:
        conversation.default_locale = generation_locale

    # === 2.7 防重入：检查同一对话是否有进行中的 Leader 会话 ===
    from datetime import timedelta
    try:
        # 先清理超时的残留会话（无进展视为卡死）
        stale_threshold = utcnow_naive() - timedelta(
            minutes=_effective_stale_session_timeout_minutes()
        )
        stale_sessions = db_session.query(LeaderSession).filter(
            LeaderSession.conversation_id == conversation_id,
            LeaderSession.state.notin_(['completed', 'stopped', 'failed']),
            LeaderSession.started_at < stale_threshold,
        ).all()
        if stale_sessions:
            run_service = DecisionRunService(db_session)
            for stale in stale_sessions:
                logger.warning(f"Auto-cleaning stale LeaderSession {stale.id} (state={stale.state}, started={stale.started_at})")
                stale.state = "failed"
                run_service.sync_from_leader_session(
                    stale.id,
                    error_code='leader_session_stale_timeout',
                )
            db_session.flush()

        active_session = db_session.query(LeaderSession).filter(
            LeaderSession.conversation_id == conversation_id,
            LeaderSession.state.notin_(['completed', 'stopped', 'failed'])
        ).first()
        if active_session:
            raise HTTPException(
                status_code=409,
                detail={'error': '该对话已有进行中的 Leader 会话，请等待完成后再启动'}
            )

        reserved_session = create_leader_session(
            db_session=db_session,
            conversation_id=conversation_id,
            message=message,
            assessment_threshold=assessment_threshold,
            system_prompt_addition=system_prompt_addition,
            locale=generation_locale,
            auto_commit=False,
        )
    except HTTPException:
        raise
    except Exception:
        # FOR UPDATE NOWAIT 获取锁失败（其他 worker 正在执行）
        raise HTTPException(
            status_code=409,
            detail={'error': '该对话已有进行中的 Leader 会话，请等待完成后再启动'}
        )

    # === 3. 处理文件内容 ===
    file_context = ''
    if uploaded_files:
        file_context_parts = ['\n\n[上传的文件内容]\n']
        file_storage = FileStorage(Config.FILE_STORAGE_PATH or 'data/files')

        for file_record in uploaded_files:
            try:
                if not file_record.file_type or file_record.file_type.startswith('text/'):
                    file_content = file_storage.get_file_content(file_record.file_path)
                    file_context_parts.append(f'\n### 文件: {file_record.filename}\n```\n{file_content[:5000]}\n```\n')
                else:
                    file_context_parts.append(f'\n### 文件: {file_record.filename}\n[二进制文件]\n')
            except Exception as e:
                logger.error(f"读取文件失败 {file_record.filename}: {e}")
                file_context_parts.append(f'\n### 文件: {file_record.filename}\n[文件读取失败]\n')

        file_context = ''.join(file_context_parts)

    # === 5. 构建上下文包 ===
    pack = ContextBuilder.build(message, file_context or None)

    # === 6. 保存用户消息 ===
    user_message_content = message
    if uploaded_files:
        user_message_content += f'\n\n[上传了 {len(uploaded_files)} 个文件: {", ".join(file_names)}]'

    user_message = Message.create_normal_message(
        conversation_id=conversation_id,
        role='user',
        content=user_message_content,
        is_review_mode=True
    )
    db_session.add(user_message)
    db_session.commit()

    # === 7. 关联文件 ===
    if uploaded_files:
        for file_record in uploaded_files:
            if file_record.conversation_id is None:
                file_record.conversation_id = conversation_id
            file_record.message_id = user_message.id
        db_session.commit()

    # === 8. 获取对话历史 ===
    history_messages = db_session.query(Message).filter_by(
        conversation_id=conversation_id
    ).order_by(Message.created_at).limit(50).all()
    history = [{'role': msg.role, 'content': msg.get_text_content()} for msg in history_messages]

    # === 9. 构建数据库模型对应的 LLM 配置 ===
    model_max_tokens = model_info['max_output_tokens']

    config = build_llm_config(
        override_max_tokens=model_max_tokens,
        model_info=model_info,
    )

    # === 10. 构建 SSE 事件生成器 ===
    async def event_generator() -> AsyncGenerator[Dict, None]:
        try:
            async for event in async_run_leader_workflow(
                conversation_id=conversation_id,
                message=pack.task_description,
                history=history,
                config=config,
                shared_evidence=pack.shared_evidence or None,
                user_id=user.id,
                skip_to_execution=skip_to_execution,
                pre_selected_agents=pre_selected_agents,
                assessment_threshold=assessment_threshold,
                system_prompt_addition=system_prompt_addition,
                locale=generation_locale,
                existing_session_id=reserved_session.id,
            ):
                yield event

        except Exception as e:
            logger.error(f"Leader session failed: {e}", exc_info=True)
            yield safe_sse_error(e, "Leader 会话执行失败")

    return create_sse_streaming_response(
        event_generator(),
        heartbeat_interval=HEARTBEAT_INTERVAL,
        max_duration=LEADER_SSE_MAX_DURATION,
    )


@router.post('/answer-questions')
async def answer_questions(
    request: AnswerQuestionsRequest,
    user: User = Depends(get_current_user),
    db_session: Session = Depends(get_db),
) -> StreamingResponse:
    """
    继续 Leader 会话（回答问题后）

    请求体:
        {
            "session_id": int,
            "answers": ["答案1", "答案2", ...]
        }

    SSE 事件类型:
        - {"type": "leader_thinking", ...} - 思考过程
        - {"type": "done", "session_id": int} - 完成
        - {"type": "error", "message": str} - 错误
    """
    user_id = user.id

    # === 1. 验证 session 归属 ===
    session = db_session.get(LeaderSession, request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail={'error': 'Session 不存在'})

    conversation = db_session.get(Conversation, session.conversation_id)
    if not conversation or conversation.user_id != user_id:
        raise HTTPException(status_code=403, detail={'error': '无权访问此 session'})

    # === 2. 构建 LLM 配置（优先从 DB 读取模型配置，与 start 端点一致）===
    model_info = _resolve_model_or_http_error(
        conversation.model_override,
        db_session,
    )
    config = build_llm_config(model_info=model_info)
    events = create_question_answer_events(
        db_session=db_session,
        session=session,
        answers=request.answers,
        config=config,
        user_id=user_id,
    )

    return create_sse_streaming_response(
        events,
        heartbeat_interval=HEARTBEAT_INTERVAL,
        max_duration=LEADER_SSE_MAX_DURATION,
    )

