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


def test_db_wrapper_get_passes_through_kwargs(monkeypatch):
    session = MagicMock()
    entity = MagicMock()
    row = object()
    session.get.return_value = row
    monkeypatch.setattr(db_module, 'SessionScoped', session)

    wrapper = db_module.DBWrapper()

    assert wrapper.get(entity, 42, with_for_update=True) is row
    session.get.assert_called_once_with(entity, 42, with_for_update=True)
