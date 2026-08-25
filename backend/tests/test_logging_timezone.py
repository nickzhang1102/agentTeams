import json
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfoNotFoundError

import app as app_module
from app import JSONFormatter, TimezoneFormatter


def _record_at_utc_time() -> logging.LogRecord:
    record = logging.LogRecord('test', logging.INFO, __file__, 1, 'message', (), None)
    record.created = datetime(2026, 8, 7, 1, 10, 12, tzinfo=timezone.utc).timestamp()
    return record


def test_text_logs_default_to_shanghai_time():
    formatter = TimezoneFormatter(
        '%(asctime)s %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )

    assert formatter.format(_record_at_utc_time()) == '2026-08-07 09:10:12 message'


def test_structured_logs_use_configured_timezone():
    formatter = JSONFormatter(
        datefmt='%Y-%m-%d %H:%M:%S',
        timezone_name='UTC',
    )

    payload = json.loads(formatter.format(_record_at_utc_time()))
    assert payload['timestamp'] == '2026-08-07 01:10:12'


def test_formatter_uses_fixed_shanghai_fallback_without_zoneinfo(monkeypatch):
    def missing_zoneinfo(_name):
        raise ZoneInfoNotFoundError('tzdata unavailable')

    monkeypatch.setattr(app_module, 'ZoneInfo', missing_zoneinfo)
    formatter = TimezoneFormatter(
        '%(asctime)s %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )

    assert formatter.format(_record_at_utc_time()) == '2026-08-07 09:10:12 message'
    assert formatter.timezone_name == 'Asia/Shanghai'
