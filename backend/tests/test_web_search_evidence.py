from unittest.mock import MagicMock, patch

from services.tools_registry import WebSearchHandler


def _response(payload):
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = payload
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
