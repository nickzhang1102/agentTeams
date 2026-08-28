import time
from unittest.mock import MagicMock, patch

from services.tools_registry import WebSearchHandler


def _response(payload):
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = payload
    return response


def _status_response(status_code):
    response = MagicMock()
    response.status_code = status_code
    return response


def test_exa_returns_one_evidence_candidate_per_search_result():
    results = []
    for index in range(1, 11):
        text = "A" * 350
        if index == 8:
            text += " critical limitation"
        results.append({
            "title": f"Result {index}",
            "url": f"https://example.com/{index}",
            "text": text,
            "score": 1 - index / 100,
        })

    handler = WebSearchHandler(exa_api_key="test-key")
    with patch("requests.post", return_value=_response({"results": results})):
        result = handler._search_exa("query")

    assert result["success"] is True
    assert len(result["evidence_items"]) == 10
    eighth = result["evidence_items"][7]
    assert eighth["rank"] == 8
    assert eighth["url"] == "https://example.com/8"
    assert eighth["provider"] == "exa"
    assert eighth["completeness"] == "passage"
    assert "critical limitation" in eighth["passage"]


def test_tavily_marks_provider_content_as_snippet_and_excludes_ai_answer():
    handler = WebSearchHandler(tavily_api_key="test-key")
    payload = {
        "answer": "Provider-generated answer without a source URL",
        "results": [{
            "title": "Source",
            "url": "https://example.com/source",
            "content": "Source snippet",
            "score": 0.8,
        }],
    }
    with patch("requests.post", return_value=_response(payload)):
        result = handler._search_tavily("query")

    assert len(result["citations"]) == 2
    assert len(result["evidence_items"]) == 1
    assert result["evidence_items"][0]["source_id"] == "https://example.com/source"
    assert result["evidence_items"][0]["completeness"] == "snippet"


# ==================== 额度错误识别与粘性退避 ====================


def test_exa_402_reports_credit_exhausted_with_clear_message():
    handler = WebSearchHandler(exa_api_key="test-key")
    with patch("requests.post", return_value=_status_response(402)):
        result = handler._search_exa("query")

    assert result["success"] is False
    assert "402" in result["error"]
    assert "credits exhausted" in result["error"]


def test_tavily_432_reports_usage_limit_with_clear_message():
    handler = WebSearchHandler(tavily_api_key="test-key")
    with patch("requests.post", return_value=_status_response(432)):
        result = handler._search_tavily("query")

    assert result["success"] is False
    assert "432" in result["error"]
    assert "usage limit" in result["error"]


def test_exa_402_marks_backoff_and_next_call_skips_exa_directly_to_tavily():
    handler = WebSearchHandler(exa_api_key="test-key", tavily_api_key="tavily-key")
    urls = []

    def _post(url, **kwargs):
        urls.append(url)
        if "exa" in url:
            return _status_response(402)
        return _response({"results": []})

    with patch("requests.post", side_effect=_post):
        first = handler.execute("query")
        assert first["success"] is True  # Tavily 接棒成功
        assert handler._exa_quota_backoff_active() is True

        second = handler.execute("query")

    assert urls[0].startswith("https://api.exa.ai")
    assert urls[1].startswith("https://api.tavily.com")
    assert second["success"] is True
    # 第二次调用：退避生效，不再请求 Exa，直接走 Tavily
    assert len(urls) == 3
    assert urls[2].startswith("https://api.tavily.com")


def test_exa_backoff_cleared_by_key_change_or_ttl_expiry():
    handler = WebSearchHandler(exa_api_key="test-key")
    assert handler._exa_quota_backoff_active() is False

    handler._mark_exa_quota_backoff()
    assert handler._exa_quota_backoff_active() is True

    # key 更换立即解除退避（管理员换了新 key）
    handler.exa_api_key = "new-key"
    assert handler._exa_quota_backoff_active() is False

    # TTL 过期后恢复尝试 Exa（月度额度刷新场景）
    handler._mark_exa_quota_backoff()
    handler._exa_backoff_until = time.monotonic() - 1
    assert handler._exa_quota_backoff_active() is False


def test_api_keys_are_trimmed_on_load():
    handler = WebSearchHandler(exa_api_key="  exa-key \n", tavily_api_key="\t tavily-key ")
    handler._load_database_credentials()
    assert handler.exa_api_key == "exa-key"
    assert handler.tavily_api_key == "tavily-key"


def test_exa_backoff_without_tavily_reports_missing_fallback():
    handler = WebSearchHandler(exa_api_key="test-key")
    with patch("requests.post", return_value=_status_response(402)):
        result = handler.execute("query")

    assert result["success"] is False
    assert "no Tavily API key" in result["error"]
