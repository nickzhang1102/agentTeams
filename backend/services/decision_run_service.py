"""决策运行生命周期、收敛门限和状态投影。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from models import (
    Conversation,
    DecisionRun,
    LeaderFinalReport,
    LeaderSession,
)
from utils.time_utils import utcnow_naive


TERMINAL_RUN_STATES = frozenset({'completed', 'failed', 'cancelled'})

LEADER_STATE_PROJECTION = {
    'idle': ('waiting_input', 'intake'),
    'assessing': ('running', 'assessment'),
    'questioning': ('waiting_input', 'assessment'),
    'forming_team': ('running', 'team_form'),
    'web_search': ('running', 'execution'),
    'monitoring': ('running', 'execution'),
    'summarizing': ('running', 'synthesis'),
    'completed': ('running', 'persistence'),
    'stopped': ('cancelled', 'persistence'),
    'failed': ('failed', 'persistence'),
}

ALLOWED_TRANSITIONS = {
    'queued': frozenset({'running', 'waiting_input', 'failed', 'cancelled'}),
    'running': frozenset({'waiting_input', 'completed', 'failed', 'cancelled'}),
    'waiting_input': frozenset({'running', 'failed', 'cancelled'}),
    'completed': frozenset(),
    'failed': frozenset(),
    'cancelled': frozenset(),
}


class DecisionRunTransitionError(ValueError):
    """当生命周期转换违反状态合同时引发。"""


@dataclass(frozen=True)
class CompletionGate:
    report_persisted: bool

    @property
    def ready(self) -> bool:
        return self.report_persisted


class DecisionRunService:
    """决策运行状态机和所有兼容性投影。"""

    def __init__(self, db_session: Session):
        self.db_session = db_session

    def create_for_leader_session(
        self,
        leader_session: LeaderSession,
        *,
        source: str = 'web',
        source_ref: Optional[str] = None,
        workflow_template_id: Optional[int] = None,
        domain_profile_key: str = 'general',
    ) -> DecisionRun:
        if leader_session.id is None:
            self.db_session.flush()
        existing = self.get_for_session(leader_session.id)
        if existing is not None:
            return existing

        run = DecisionRun(
            leader_session_id=leader_session.id,
            conversation_id=leader_session.conversation_id,
            source=source,
            source_ref=source_ref,
            workflow_template_id=workflow_template_id,
            domain_profile_key=domain_profile_key or 'general',
            state='queued',
            quality_status='pending',
            current_stage='intake',
            degradation_reasons=[],
        )
        self.db_session.add(run)
        self.db_session.flush()
        return run

    def get(self, run_id: UUID | str, *, for_update: bool = False) -> Optional[DecisionRun]:
        try:
            normalized = UUID(str(run_id))
        except (TypeError, ValueError, AttributeError):
            return None
        query = self.db_session.query(DecisionRun).filter(DecisionRun.run_id == normalized)
        if for_update:
            query = query.with_for_update()
        return query.first()

    def get_for_session(
        self,
        leader_session_id: int,
        *,
        for_update: bool = False,
    ) -> Optional[DecisionRun]:
        query = self.db_session.query(DecisionRun).filter(
            DecisionRun.leader_session_id == leader_session_id
        )
        if for_update:
            query = query.with_for_update()
        return query.first()

    def transition(
        self,
        run_id: UUID | str,
        expected_state: str,
        target_state: str,
        *,
        stage: str,
        error_code: Optional[str] = None,
    ) -> DecisionRun:
        run = self.get(run_id, for_update=True)
        if run is None:
            raise DecisionRunTransitionError("DecisionRun not found")
        if run.state == target_state:
            return run
        if run.state != expected_state:
            raise DecisionRunTransitionError(
                f"DecisionRun expected {expected_state}, found {run.state}"
            )
        return self._apply_transition(run, target_state, stage, error_code=error_code)

    def mark_started(self, leader_session_id: int, *, stage: str = 'assessment') -> Optional[DecisionRun]:
        run = self.get_for_session(leader_session_id, for_update=True)
        if run is None:
            return None
        if run.state in TERMINAL_RUN_STATES:
            return run
        if run.state != 'running':
            self._apply_transition(run, 'running', stage)
        else:
            self._set_stage(run, stage)
        return run

    def set_stage(self, leader_session_id: int, stage: str) -> Optional[DecisionRun]:
        run = self.get_for_session(leader_session_id, for_update=True)
        if run is None or run.state in TERMINAL_RUN_STATES:
            return run
        self._set_stage(run, stage)
        return run

    def sync_from_leader_session(
        self,
        leader_session_id: int,
        *,
        error_code: Optional[str] = None,
    ) -> Optional[DecisionRun]:
        leader_session = self.db_session.get(LeaderSession, leader_session_id)
        run = self.get_for_session(leader_session_id, for_update=True)
        if leader_session is None or run is None:
            return run
        target_state, stage = LEADER_STATE_PROJECTION.get(
            leader_session.state,
            ('running', 'intake'),
        )
        if leader_session.state == 'completed':
            self._set_stage(run, 'persistence')
            return self._converge_completion(run)
        if run.state == target_state:
            self._set_stage(run, stage)
            if error_code:
                run.error_code = error_code
            return run
        if run.state in TERMINAL_RUN_STATES:
            return run
        self._apply_transition(run, target_state, stage, error_code=error_code)
        return run

    def mark_report_persisted(
        self,
        leader_session_id: int,
        *,
        quality_status: str = 'passed',
        degradation_reasons: Optional[Iterable[str]] = None,
    ) -> Optional[DecisionRun]:
        run = self.get_for_session(leader_session_id, for_update=True)
        if run is None:
            return None
        self.mark_quality(run, quality_status, degradation_reasons or ())
        self._set_stage(run, 'persistence')
        return self._converge_completion(run)

    def mark_quality(
        self,
        run: DecisionRun,
        status: str,
        reasons: Iterable[str] = (),
    ) -> DecisionRun:
        normalized_reasons = list(dict.fromkeys(
            str(reason).strip() for reason in reasons if str(reason).strip()
        ))
        if status == 'normal':
            status = 'passed'
        existing_reasons = list(run.degradation_reasons or [])
        if run.quality_status == 'blocked' and status != 'blocked':
            status = 'blocked'
        elif run.quality_status == 'degraded':
            normalized_reasons = list(dict.fromkeys([
                *existing_reasons,
                *normalized_reasons,
            ]))
            if status == 'passed':
                status = 'degraded'
        if status not in {'pending', 'passed', 'degraded', 'blocked'}:
            raise ValueError(f"Invalid DecisionRun quality status: {status}")
        if status == 'degraded' and not normalized_reasons:
            raise ValueError("Degraded DecisionRun requires a reason code")
        run.quality_status = status
        run.degradation_reasons = normalized_reasons
        run.updated_at = utcnow_naive()
        self.db_session.flush()
        return run

    def completion_gate(self, run: DecisionRun) -> CompletionGate:
        report_persisted = self.db_session.query(LeaderFinalReport.id).filter(
            LeaderFinalReport.leader_session_id == run.leader_session_id
        ).first() is not None
        return CompletionGate(report_persisted)

    def projection(self, run: DecisionRun) -> dict:
        projection = run.to_dict()
        projection['legacy'] = False
        projection['leader_session_id'] = run.leader_session_id
        projection['conversation_id'] = run.conversation_id
        projection['final_report_id'] = self.db_session.query(LeaderFinalReport.id).filter(
            LeaderFinalReport.leader_session_id == run.leader_session_id
        ).scalar()
        return projection

    @staticmethod
    def legacy_projection(leader_session: LeaderSession) -> dict:
        state, stage = LEADER_STATE_PROJECTION.get(
            leader_session.state,
            ('running', 'intake'),
        )
        if leader_session.state == 'completed':
            state = 'completed'
        return {
            'run_id': None,
            'legacy': True,
            'leader_session_id': leader_session.id,
            'conversation_id': leader_session.conversation_id,
            'source': None,
            'source_ref': None,
            'state': state,
            'quality_status': None,
            'current_stage': stage,
            'degradation_reasons': [],
            'error_code': None,
            'final_report_id': None,
            'created_at': leader_session.started_at.isoformat() + 'Z' if leader_session.started_at else None,
            'started_at': leader_session.started_at.isoformat() + 'Z' if leader_session.started_at else None,
            'completed_at': leader_session.completed_at.isoformat() + 'Z' if leader_session.completed_at else None,
            'updated_at': None,
        }

    def projection_for_session(self, leader_session: LeaderSession) -> dict:
        run = self.get_for_session(leader_session.id)
        return self.projection(run) if run is not None else self.legacy_projection(leader_session)

    def owner_can_access(self, run: DecisionRun, user_id: int) -> bool:
        if run.conversation_id is None:
            return False
        return self.db_session.query(Conversation.id).filter(
            Conversation.id == run.conversation_id,
            Conversation.user_id == user_id,
        ).first() is not None

    def _converge_completion(self, run: DecisionRun) -> DecisionRun:
        if run.state in TERMINAL_RUN_STATES:
            return run
        if self.completion_gate(run).ready:
            if run.state == 'queued':
                self._apply_transition(run, 'running', 'persistence')
            return self._apply_transition(run, 'completed', 'persistence')
        return run

    def _apply_transition(
        self,
        run: DecisionRun,
        target_state: str,
        stage: str,
        *,
        error_code: Optional[str] = None,
    ) -> DecisionRun:
        if target_state == run.state:
            return run
        if target_state not in ALLOWED_TRANSITIONS.get(run.state, frozenset()):
            raise DecisionRunTransitionError(
                f"Invalid DecisionRun transition: {run.state} -> {target_state}"
            )
        now = utcnow_naive()
        run.state = target_state
        run.current_stage = stage
        run.error_code = error_code
        run.updated_at = now
        if target_state == 'running' and run.started_at is None:
            run.started_at = now
        if target_state in TERMINAL_RUN_STATES:
            run.completed_at = run.completed_at or now
        self.db_session.flush()
        return run

    def _set_stage(self, run: DecisionRun, stage: str) -> None:
        valid = {'intake', 'assessment', 'team_form', 'execution', 'review', 'synthesis', 'persistence'}
        if stage not in valid:
            raise ValueError(f"Invalid DecisionRun stage: {stage}")
        run.current_stage = stage
        run.updated_at = utcnow_naive()
        self.db_session.flush()
