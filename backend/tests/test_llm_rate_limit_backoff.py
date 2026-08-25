"""429 限流退避的单元测试。

Retry-After 与指数退避共用同一封顶：服务端返回的大等待值
不得长期占住全局并发槽位冻结工作流线程。
"""

import sys
import os
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.llm_service import (
    RATE_LIMIT_BACKOFF_BASE,
    RATE_LIMIT_RETRY_AFTER_CAP_SECONDS,
    _rate_limit_backoff,
)


def _error_with_retry_after(value):
    """构造携带 Retry-After 响应头的模拟限流错误。"""
    error = Exception('rate limited')
    error.response = SimpleNamespace(headers={'Retry-After': str(value)})
    return error


def test_retry_after_large_value_is_capped():
    assert _rate_limit_backoff(_error_with_retry_after(3600), 1) == (
        RATE_LIMIT_RETRY_AFTER_CAP_SECONDS
    )


def test_retry_small_value_is_respected():
    assert _rate_limit_backoff(_error_with_retry_after(5), 1) == 5.0


def test_exponential_branch_still_capped_without_header():
    error = Exception('rate limited')
    assert _rate_limit_backoff(error, 10) == RATE_LIMIT_RETRY_AFTER_CAP_SECONDS
    assert _rate_limit_backoff(error, 1) == RATE_LIMIT_BACKOFF_BASE


def test_invalid_retry_after_falls_back_to_exponential():
    assert _rate_limit_backoff(_error_with_retry_after('not-a-number'), 2) == (
        RATE_LIMIT_BACKOFF_BASE * 2
    )
