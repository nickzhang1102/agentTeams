from context.evidence_context import EvidenceContextBuilder


def _evidence(index, *, source_id=None, relation=None):
    item = {
        "evidence_id": f"ev_{index}",
        "source_id": source_id or f"source-{index}",
        "title": f"Evidence {index}",
        "excerpt": f"excerpt {index}",
        "raw_ref": f"raw_tool_results.ev_{index}",
    }
    if relation:
        item["relation"] = relation
    return item


def test_preferred_eighth_result_is_selected_before_earlier_results():
    evidence_map = [_evidence(index) for index in range(1, 11)]
    raw = {
        f"ev_{index}": {"passage": f"passage {index}"}
        for index in range(1, 11)
    }
    selection = EvidenceContextBuilder(
        total_char_budget=200,
        item_char_budget=100,
        item_limit=1,
    ).build(evidence_map, raw_tool_results=raw, preferred_refs=["ev_8"])

    assert selection.selected_ids == ("ev_8",)
    assert "passage 8" in selection.text
    assert selection.dropped_count == 9


def test_passage_content_after_300_chars_reaches_context():
    passage = "A" * 350 + " critical limitation after excerpt"
    selection = EvidenceContextBuilder(
        total_char_budget=1000,
        item_char_budget=800,
        item_limit=2,
    ).build(
        [_evidence(1)],
        raw_tool_results={"ev_1": {"passage": passage}},
    )

    assert "critical limitation after excerpt" in selection.text


def test_conflicting_evidence_is_kept_before_ordinary_repeated_sources():
    evidence_map = [
        _evidence(1, source_id="same"),
        _evidence(2, source_id="same"),
        _evidence(3, relation="contradicts"),
    ]
    selection = EvidenceContextBuilder(
        total_char_budget=500,
        item_char_budget=100,
        item_limit=2,
    ).build(evidence_map)

    assert selection.selected_ids == ("ev_3", "ev_1")
    assert "(contradicts)" in selection.text
