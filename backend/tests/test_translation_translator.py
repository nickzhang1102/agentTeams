from contextlib import contextmanager
import json
from types import SimpleNamespace

import pytest

from translation.payload import normalize_translation_payload
from translation.translator import (
    TranslationIntegrityError,
    batch_translation_slots,
    translate_normalized_payload,
)


class FakeLLM:
    model = 'translation-test-model'

    def __init__(self, transform):
        self.transform = transform
        self.calls = []

    def get_context_limit(self):
        return 4096

    def get_max_output_tokens(self):
        return 2048

    def estimate_tokens(self, text):
        return max(1, len(text) // 2)

    def call_sync(self, prompt, **kwargs):
        self.calls.append((prompt, kwargs))
        inputs = json.loads(prompt.split('Input:\n', 1)[1])
        return json.dumps([
            {'id': item['id'], 'text': self.transform(item['text'])}
            for item in inputs
        ], ensure_ascii=False)

    @contextmanager
    def capture_usage(self):
        yield {'input_tokens': 10, 'output_tokens': 8}


def _message(text):
    return SimpleNamespace(
        role='assistant',
        message_type='normal',
        leader_session_id=None,
        content={'text': text},
        content_locale='zh-CN',
    )


def test_translator_preserves_markdown_code_urls_ids_evidence_and_numbers():
    source_text = (
        '结论 42% 见 https://example.com/a 和 [ev_1]。\n\n'
        '```python\nvalue = 42\n```\n使用 `run_2` 执行。'
    )
    normalized = normalize_translation_payload('message', _message(source_text))
    llm = FakeLLM(lambda text: text.replace('结论', 'Conclusion').replace('见', 'see').replace('使用', 'Use').replace('执行', 'to execute'))

    translated = translate_normalized_payload(
        normalized,
        'zh-CN',
        'en-US',
        llm,
    )

    assert translated['text'].startswith('Conclusion 42%')
    assert 'https://example.com/a' in translated['text']
    assert '[ev_1]' in translated['text']
    assert '```python\nvalue = 42\n```' in translated['text']
    assert '`run_2`' in translated['text']


def test_translator_rejects_changed_protected_text():
    normalized = normalize_translation_payload(
        'message',
        _message('参考 https://example.com/a，证据 [ev_2]，评分 88。'),
    )
    llm = FakeLLM(lambda text: text.replace('https://example.com/a', 'https://evil.test'))

    with pytest.raises(TranslationIntegrityError, match='protected text changed'):
        translate_normalized_payload(normalized, 'zh-CN', 'en-US', llm)


def test_translator_preserves_complete_evidence_id_reference():
    normalized = normalize_translation_payload(
        'message',
        _message('结论依据 [evidence_id:REFERENCE_ALPHA]。'),
    )
    llm = FakeLLM(
        lambda text: text.replace('结论依据', 'Evidence').replace(
            'REFERENCE_ALPHA',
            'REFERENCE_BETA',
        )
    )

    with pytest.raises(TranslationIntegrityError, match='protected text changed'):
        translate_normalized_payload(normalized, 'zh-CN', 'en-US', llm)


def test_slot_batches_respect_context_budget_and_reject_oversize_slot():
    normalized = normalize_translation_payload(
        'leader_final_report',
        SimpleNamespace(
            report='正文一',
            content_locale='zh-CN',
            executive_summary={'recommendations': ['建议二']},
            structured_report={'recommendations': ['建议三']},
        ),
    )
    batches = batch_translation_slots(
        normalized.slots,
        token_budget=34,
        estimate_tokens=lambda text: 2,
    )
    assert len(batches) == len(normalized.slots)

    with pytest.raises(TranslationIntegrityError, match='context budget'):
        batch_translation_slots(
            normalized.slots,
            token_budget=1,
            estimate_tokens=lambda text: 2,
        )


def test_large_translation_caps_output_budget_and_uses_background_timeout():
    normalized = normalize_translation_payload(
        'message',
        _message('长篇分析内容' * 4000),
    )
    llm = FakeLLM(lambda text: text)
    llm.get_context_limit = lambda: 1_000_000
    llm.get_max_output_tokens = lambda: 32_768

    translate_normalized_payload(normalized, 'zh-CN', 'en-US', llm)

    assert len(llm.calls) == 1
    _, kwargs = llm.calls[0]
    assert kwargs['max_tokens'] == 16384
    assert kwargs['timeout'] == 240.0
    assert kwargs['reject_truncated'] is True


def test_translation_reserves_expansion_budget_below_output_cap():
    normalized = normalize_translation_payload(
        'message',
        _message('中等长度内容' * 100),
    )
    llm = FakeLLM(lambda text: text)
    llm.get_context_limit = lambda: 100_000
    llm.get_max_output_tokens = lambda: 16_384

    translate_normalized_payload(normalized, 'zh-CN', 'en-US', llm)

    _, kwargs = llm.calls[0]
    estimated_output = llm.estimate_tokens(normalized.slots[0].text)
    assert kwargs['max_tokens'] == estimated_output * 2 + 256


def test_long_markdown_is_split_and_each_request_fits_context_window():
    source_text = (
        '# Analysis\n\n'
        + ('A clinically relevant paragraph with supporting detail. ' * 80)
        + '\n\n```text\nprotected code block\n```\n\n'
        + ('A second section with recommendations and caveats. ' * 80)
    )
    normalized = normalize_translation_payload('message', _message(source_text))
    llm = FakeLLM(lambda text: text)
    llm.get_context_limit = lambda: 4096
    llm.get_max_output_tokens = lambda: 4096

    translated = translate_normalized_payload(normalized, 'zh-CN', 'en-US', llm)

    assert translated['text'] == source_text
    assert len(llm.calls) > 1
    for prompt, kwargs in llm.calls:
        request_tokens = (
            llm.estimate_tokens(prompt)
            + llm.estimate_tokens(kwargs['system_prompt'])
            + 64
            + kwargs['max_tokens']
        )
        assert request_tokens <= llm.get_context_limit()


def test_oversize_fenced_block_is_reassembled_without_sending_it_to_llm():
    protected = '```text\n' + ('protected ' * 2000) + '\n```'
    source_text = f'Before\n\n{protected}\n\nAfter'
    normalized = normalize_translation_payload(
        'message',
        _message(source_text),
    )
    llm = FakeLLM(lambda text: text)

    translated = translate_normalized_payload(normalized, 'zh-CN', 'en-US', llm)

    assert translated['text'] == source_text
    assert all(protected not in prompt for prompt, _ in llm.calls)
