from types import SimpleNamespace
from unittest.mock import MagicMock

from leader.leader_persistence import _persist_agent_results, load_agent_results
from models import LeaderFinalReport


def test_persist_agent_results_writes_content_locale():
    db_session = MagicMock()
    db_session.query.return_value.filter_by.return_value.order_by.return_value.first.return_value = None

    _persist_agent_results(
        db_session=db_session,
        conversation_id=10,
        session_id=20,
        results=[{
            "agent_id": "researcher",
            "agent_name": "Researcher",
            "success": True,
            "content": "English report",
            "content_locale": "en-US",
        }],
    )

    saved = db_session.add.call_args.args[0]
    assert saved.content_locale == "en-US"
    db_session.commit.assert_called_once()


def test_load_agent_results_restores_content_locale():
    db_session = MagicMock()
    db_session.query.return_value.filter_by.return_value.order_by.return_value.all.return_value = [
        SimpleNamespace(
            agent_id="researcher",
            agent_name="Researcher",
            content="English report",
            content_locale="en-US",
            summary=None,
            structured_report=None,
            raw_tool_results={"ev_1": {"result": "原文"}},
            evidence_map=[],
            status="success",
            error=None,
            tool_calls=[],
            tokens_used=12,
            execution_time=0.5,
            decomposition=None,
        )
    ]

    results = load_agent_results(db_session, session_id=20)

    assert results[0]["content_locale"] == "en-US"
    assert results[0]["raw_tool_results"]["ev_1"]["result"] == "原文"


def test_final_report_to_dict_exposes_content_locale():
    report = LeaderFinalReport(
        conversation_id=10,
        leader_session_id=20,
        report="English report",
        content_locale="en-US",
    )

    assert report.to_dict()["content_locale"] == "en-US"
