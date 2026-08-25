"""Owner read projection for unified DecisionRun records."""

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from api.deps import get_current_user
from database import get_db
from models import User
from services.decision_evidence_service import (
    DecisionEvidenceForbidden,
    DecisionEvidenceNotFound,
    DecisionEvidenceService,
    DecisionEvidenceUnavailable,
    LegacyEvidenceUnresolvable,
)
from services.decision_run_service import DecisionRunService


router = APIRouter(prefix="/api/decision-runs", tags=["decision-runs"])
legacy_router = APIRouter(prefix="/api/leader/sessions", tags=["decision-evidence"])


@router.get("/{run_id}")
def get_decision_run(
    run_id: str,
    response: Response,
    user: User = Depends(get_current_user),
    db_session: Session = Depends(get_db),
):
    """Return a minimal owner-only run projection without report or input content."""
    service = DecisionRunService(db_session)
    run = service.get(run_id)
    if run is None or not service.owner_can_access(run, user.id):
        raise HTTPException(status_code=404, detail={"error": "decision_run_not_found"})
    response.headers["Cache-Control"] = "no-store"
    return service.projection(run)


@router.get("/{run_id}/evidence/{evidence_id}")
def get_decision_evidence(
    run_id: str,
    evidence_id: str,
    response: Response,
    user: User = Depends(get_current_user),
    db_session: Session = Depends(get_db),
):
    """Return one bounded evidence passage to the run owner."""
    service = DecisionEvidenceService(db_session)
    try:
        payload = service.detail_for_owner(run_id, evidence_id, user.id)
    except DecisionEvidenceForbidden as exc:
        raise HTTPException(status_code=403, detail={"error": str(exc)}) from exc
    except DecisionEvidenceNotFound as exc:
        _commit_observation(db_session)
        raise HTTPException(status_code=404, detail={"error": str(exc)}) from exc
    except DecisionEvidenceUnavailable as exc:
        _commit_observation(db_session)
        raise HTTPException(status_code=410, detail={"error": str(exc)}) from exc
    response.headers["Cache-Control"] = "private, no-store"
    return payload


@router.get("/{run_id}/evidence-metrics")
def get_decision_evidence_metrics(
    run_id: str,
    response: Response,
    user: User = Depends(get_current_user),
    db_session: Session = Depends(get_db),
):
    """Return non-content evidence quality counters to the run owner."""
    service = DecisionEvidenceService(db_session)
    try:
        payload = service.quality_metrics_for_owner(run_id, user.id)
    except (DecisionEvidenceForbidden, DecisionEvidenceNotFound) as exc:
        raise HTTPException(
            status_code=404,
            detail={"error": "decision_run_not_found"},
        ) from exc
    response.headers["Cache-Control"] = "private, no-store"
    return payload


@legacy_router.get("/{session_id}/evidence/{evidence_id}")
def get_session_evidence(
    session_id: int,
    evidence_id: str,
    response: Response,
    user: User = Depends(get_current_user),
    db_session: Session = Depends(get_db),
):
    """Resolve owner evidence through DecisionRun or an explicit legacy fallback."""
    service = DecisionEvidenceService(db_session)
    try:
        payload = service.detail_for_session_owner(session_id, evidence_id, user.id)
    except DecisionEvidenceForbidden as exc:
        raise HTTPException(status_code=403, detail={"error": str(exc)}) from exc
    except DecisionEvidenceNotFound as exc:
        _commit_observation(db_session)
        raise HTTPException(status_code=404, detail={"error": str(exc)}) from exc
    except DecisionEvidenceUnavailable as exc:
        _commit_observation(db_session)
        raise HTTPException(status_code=410, detail={"error": str(exc)}) from exc
    except LegacyEvidenceUnresolvable as exc:
        raise HTTPException(status_code=422, detail={"error": str(exc)}) from exc
    response.headers["Cache-Control"] = "private, no-store"
    return payload


def _commit_observation(db_session: Session) -> None:
    try:
        db_session.commit()
    except Exception:
        db_session.rollback()
