from types import SimpleNamespace

import pytest

from translation.payload import (
    canonical_source_hash,
    normalize_translation_payload,
)


def test_message_normalizer_accepts_only_supported_ai_content():
    assistant = SimpleNamespace(
        role='assistant',
        message_type='normal',
        leader_session_id=None,
        content={'text': '分析结论'},
        content_locale='zh-CN',
    )
    normalized = normalize_translation_payload('message', assistant)

    assert normalized.payload == {'text': '分析结论'}
    assert [slot.path for slot in normalized.slots] == ['/text']

    for rejected in (
        SimpleNamespace(
            role='user',
            message_type='normal',
            leader_session_id=None,
            content={'text': '用户输入'},
            content_locale='zh-CN',
        ),
        SimpleNamespace(
            role='assistant',
            message_type='answer',
            leader_session_id=8,
            content={'text': 'Leader 回答'},
            content_locale='zh-CN',
        ),
        SimpleNamespace(
            role='assistant',
            message_type='normal',
            leader_session_id=None,
            content={'text': '未知语言'},
            content_locale=None,
        ),
    ):
        with pytest.raises(ValueError, match='SOURCE_NOT_TRANSLATABLE'):
            normalize_translation_payload('message', rejected)


def test_agent_result_normalizer_excludes_raw_evidence_and_machine_values():
    result = SimpleNamespace(
        content='## Agent 分析\n正文 [ev_1]',
        content_locale='zh-CN',
        summary={
            'one_sentence': '核心结论',
            'key_findings': ['发现一'],
            'confidence': 0.9,
            'evidence_refs': ['ev_1'],
        },
        structured_report={
            'summary': {'recommendations': ['建议一'], 'confidence': 0.8},
            'markdown_report': '## Agent 分析\n正文 [ev_1]',
            'visual_blocks': [{
                'block_id': 'risk-main',
                'type': 'risk_matrix',
                'title': '风险矩阵',
                'data': {
                    'risks': [{
                        'risk': '供应风险',
                        'likelihood': 'high',
                        'mitigation': '准备替代供应商',
                        'source_id': 'source-1',
                        'url': 'https://example.com/source',
                        'machine_state': 'stable',
                    }],
                },
                'evidence_refs': ['ev_1'],
            }],
            'quality_status': 'warning',
        },
        raw_tool_results={'ev_1': {'content': '原始工具正文'}},
        evidence_map=[{'evidence_id': 'ev_1', 'excerpt': '原始证据摘录'}],
        tool_calls=[{'output': '工具响应'}],
        decomposition={'reasoning': '分解计划'},
    )

    normalized = normalize_translation_payload('leader_agent_result', result)
    serialized = str(normalized.payload)
    slot_paths = {slot.path for slot in normalized.slots}

    assert set(normalized.payload) == {'content', 'summary', 'structured_report'}
    assert '原始工具正文' not in serialized
    assert '原始证据摘录' not in serialized
    assert '工具响应' not in serialized
    assert '分解计划' not in serialized
    assert '/summary/one_sentence' in slot_paths
    assert '/structured_report/visual_blocks/0/title' in slot_paths
    assert '/structured_report/visual_blocks/0/data/risks/0/mitigation' in slot_paths
    assert normalized.protected_manifest[
        '/structured_report/visual_blocks/0/block_id'
    ] == 'risk-main'
    assert normalized.protected_manifest[
        '/structured_report/visual_blocks/0/data/risks/0/source_id'
    ] == 'source-1'
    assert normalized.protected_manifest[
        '/structured_report/visual_blocks/0/data/risks/0/url'
    ] == 'https://example.com/source'
    assert normalized.protected_manifest[
        '/structured_report/visual_blocks/0/data/risks/0/machine_state'
    ] == 'stable'


def test_final_report_payload_has_stable_hash_and_visible_change_sensitivity():
    report = SimpleNamespace(
        report='# 报告\n正文',
        content_locale='zh-CN',
        executive_summary={
            'recommendations': ['先试点'],
            'confidence': 0.8,
        },
        structured_report={
            'recommendations': ['先试点'],
            'evidence_refs': ['ev_2'],
            'markdown_report': '# 报告\n正文',
        },
        evidence_map=[{'excerpt': '不得进入 payload'}],
    )
    normalized = normalize_translation_payload('leader_final_report', report)

    reordered = {
        'structured_report': normalized.payload['structured_report'],
        'executive_summary': normalized.payload['executive_summary'],
        'report': normalized.payload['report'],
    }
    assert canonical_source_hash(reordered) == normalized.source_hash

    changed = dict(normalized.payload)
    changed['report'] = '# 报告\n正文已修改'
    assert canonical_source_hash(changed) != normalized.source_hash
    assert '不得进入 payload' not in str(normalized.payload)
    assert normalized.protected_manifest[
        '/structured_report/evidence_refs'
    ] == ['ev_2']
