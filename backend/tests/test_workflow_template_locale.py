from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from api import workflow_template_api
from schemas.workflow_template import ApplyTemplateRequest


def _request(accept_language: str = "zh-CN") -> Request:
    return Request({
        "type": "http",
        "method": "POST",
        "path": "/api/workflow-templates/1/apply",
        "headers": [(b"accept-language", accept_language.encode("ascii"))],
    })


@pytest.mark.asyncio
async def test_apply_template_rejects_invalid_locale_before_side_effects():
    body = ApplyTemplateRequest(
        conversation_id=42,
        message="test",
        locale="fr-FR",
    )
    user = SimpleNamespace(id=7, is_admin=False)
    db = MagicMock()

    with patch.object(workflow_template_api, "WorkflowTemplateService") as service_cls, \
         patch("api.leader_api._start_leader_workflow", new_callable=AsyncMock) as start:
        with pytest.raises(HTTPException) as exc_info:
            await workflow_template_api.apply_template.__wrapped__(
                template_id=1,
                request=_request(),
                body=body,
                user=user,
                db=db,
            )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "UNSUPPORTED_LOCALE"
    service_cls.assert_not_called()
    db.get.assert_not_called()
    db.commit.assert_not_called()
    start.assert_not_awaited()


@pytest.mark.asyncio
async def test_apply_template_forwards_explicit_locale_and_header():
    body = ApplyTemplateRequest(
        conversation_id=42,
        message="test",
        locale="en-US",
    )
    user = SimpleNamespace(id=7, is_admin=False)
    template = SimpleNamespace(
        skip_assessment=False,
        assessment_threshold=70,
        system_prompt_addition="template prompt",
        usage_count=2,
        last_used_at=None,
    )
    conversation = SimpleNamespace(user_id=7, category="other")
    db = MagicMock()
    db.get.return_value = conversation
    service = MagicMock()
    service.get_template.return_value = template
    service.resolve_agent_ids.return_value = []
    service.resolve_case_category.return_value = "other"

    with patch.object(workflow_template_api, "WorkflowTemplateService", return_value=service), \
         patch("api.leader_api._start_leader_workflow", new_callable=AsyncMock, return_value="stream") as start:
        response = await workflow_template_api.apply_template.__wrapped__(
            template_id=1,
            request=_request("zh-CN"),
            body=body,
            user=user,
            db=db,
        )

    assert response == "stream"
    assert template.usage_count == 3
    start.assert_awaited_once()
    kwargs = start.await_args.kwargs
    assert kwargs["explicit_locale"] == "en-US"
    assert kwargs["accept_language"] == "zh-CN"

