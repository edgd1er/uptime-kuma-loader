import sys
import pytest
from unittest.mock import Mock
import logging

# importer la fonction à tester
from src.kuma_load import get_monitors

# Fixture pour intercepter sys.exit
@pytest.fixture(autouse=True)
def fake_sys_exit(monkeypatch):
    exits = {"called": False, "code": None}
    def _fake_exit(code=0):
        exits["called"] = True
        exits["code"] = code
        raise SystemExit(code)
    monkeypatch.setattr(sys, "exit", _fake_exit)
    return exits

def test_get_monitors_api_none_raises():
    # La fonction n'anticipe pas api=None ; on s'attend à une AttributeError
    with pytest.raises(AttributeError):
        get_monitors(None)

def test_get_monitors_api_raises_exception_calls_disconnect_and_exit(caplog, fake_sys_exit):
    api = Mock()
    api.get_monitors.side_effect = RuntimeError("boom")
    api.disconnect = Mock()

    caplog.set_level(logging.ERROR)
    with pytest.raises(SystemExit) as excinfo:
        get_monitors(api)

    assert fake_sys_exit["called"] is True
    assert fake_sys_exit["code"] == 5
    assert excinfo.value.code == 5
    api.disconnect.assert_called_once()
    assert any("Failed to fetch existing monitors" in r.getMessage() for r in caplog.records)

def test_get_monitors_empty_list():
    api = Mock()
    api.get_monitors.return_value = []

    existing_config, existing_monitors = get_monitors(api)

    assert existing_config == []
    assert existing_monitors == {}

def test_get_monitors_with_monitors():
    api = Mock()
    sample = [
        {"id": 10, "name": "site-a", "url": "https://a.example"},
        {"id": 11, "name": "site-b", "url": "https://b.example"},
        {"id": 12, "no_name": True},  # doit être ignoré car pas de "name"
        {"id": 13, "name": "site-c"}, # valide même sans autres champs
        {"name": "no_id"},            # ignoré car pas d'id
    ]
    api.get_monitors.return_value = sample

    existing_config, existing_monitors = get_monitors(api)

    # existing_config doit être la liste brute
    assert existing_config == sample

    # existing_monitors doit contenir uniquement les entrées ayant "name" et "id"
    assert "site-a" in existing_monitors
    assert existing_monitors["site-a"]["id"] == 10
    assert "site-b" in existing_monitors
    assert existing_monitors["site-b"]["url"] == "https://b.example"
    assert "site-c" in existing_monitors
    assert existing_monitors["site-c"]["id"] == 13

    # entrées invalides ignorées
    assert "no_id" not in existing_monitors
    # l'élément sans "name" ne doit pas apparaître
    assert not any(mon.get("no_name") for mon in existing_monitors.values())
