import sys
import pytest
from types import SimpleNamespace
from unittest.mock import Mock
import logging

# importer la fonction à tester
from src.kuma_load.kuma_load import get_tags

# Fixtures utiles
@pytest.fixture(autouse=True)
def reset_sys_exit(monkeypatch):
    """Empêcher sys.exit réel pendant les tests; capturer l'appel."""
    exits = {"called": False, "code": None}

    def fake_exit(code=0):
        exits["called"] = True
        exits["code"] = code
        raise SystemExit(code)

    monkeypatch.setattr(sys, "exit", fake_exit)
    return exits

def test_get_tags_api_none():
    result = get_tags(None)
    assert result == []


def test_get_tags_api_raises_exception(caplog, reset_sys_exit):
    # Préparer un mock api dont get_tags lève une exception
    api = Mock()
    api.get_tags.side_effect = RuntimeError("boom")

    caplog.set_level(logging.ERROR)
    with pytest.raises(SystemExit) as excinfo:
        get_tags(api)

    # sys.exit(5) doit avoir été appelé
    assert reset_sys_exit["called"] is True
    assert reset_sys_exit["code"] == 5
    assert excinfo.value.code == 5

    # Vérifier qu'un log d'erreur a été émis
    assert any("Failed to get existing tags" in r.message for r in caplog.records)


def test_get_tags_empty_list(caplog):
    # api.get_tags retourne une liste vide
    api = Mock()
    api.get_tags.return_value = []

    caplog.set_level(logging.INFO)
    existing_tags, existing_tags_id = get_tags(api)

    assert existing_tags == []
    assert existing_tags_id == {}

    # Vérifier logs d'info (0 tags)
    assert any("existing_tags: 0" in r.getMessage() for r in caplog.records)


def test_get_tags_with_tags(caplog):
    # api.get_tags retourne des tags valides
    api = Mock()
    sample = [
        {"id": 1, "name": "alpha", "other": "x"},
        {"id": 2, "name": "beta", "other": "y"},
    ]
    api.get_tags.return_value = sample

    caplog.set_level(logging.DEBUG)
    existing_tags, existing_tags_id = get_tags(api)

    # Vérifications de base
    assert existing_tags == sample
    # existing_tags_id doit être un dict mappant id -> tag dict
    assert isinstance(existing_tags_id, dict)
    assert existing_tags_id[1]["name"] == "alpha"
    assert existing_tags_id[2]["name"] == "beta"
    # Vérifier que les noms extraits correspondent
    names = [t["name"] for t in existing_tags]
    assert names == ["alpha", "beta"]

    # Vérifier qu'au moins un message debug contient les noms des tags
    assert any("alpha" in r.getMessage() and "beta" in r.getMessage() for r in caplog.records)
