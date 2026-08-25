from unittest.mock import MagicMock

import db as db_module


def test_db_wrapper_delegates_nested_transaction(monkeypatch):
    session = MagicMock()
    savepoint = object()
    session.begin_nested.return_value = savepoint
    monkeypatch.setattr(db_module, 'SessionScoped', session)

    result = db_module.DBWrapper().begin_nested()

    assert result is savepoint
    session.begin_nested.assert_called_once_with()
