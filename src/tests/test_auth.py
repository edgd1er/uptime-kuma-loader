import pytest
from types import SimpleNamespace
from src.kuma_load import get_token_from_kuma_api


class DummyApi(SimpleNamespace):
  # SimpleNamespace permet d'attribuer dynamiquement les méthodes attendues
  pass


def test_no_api_returns_none(caplog):
  res = get_token_from_kuma_api(None, username="u", password="p")
  assert res is None
  assert "kuma_api is None" in caplog.text


def test_no_credentials_returns_none(caplog):
  api = DummyApi()
  res = get_token_from_kuma_api(api)
  assert res is None
  assert "No credentials provided" in caplog.text


def test_login_by_token_success():
  # api.login_by_token returns dict with token
  api = DummyApi(login_by_token=lambda t: {"token": "abc"})
  res = get_token_from_kuma_api(api, token="tok")
  assert res == "abc"


def test_login_by_token_no_token_returned(caplog):
  api = DummyApi(login_by_token=lambda t: {"msg": "ok"})
  res = get_token_from_kuma_api(api, token="tok")
  assert res is None
  assert "Authentication succeeded but no token returned" in caplog.text


def test_login_username_password_success():
  api = DummyApi(login=lambda u, p: {"token": "xyz"})
  res = get_token_from_kuma_api(api, username="u", password="p")
  assert res == "xyz"


def test_login_raises_exception_disconnect_called_and_none(monkeypatch):
  disconnected = {"called": False}

  def login_raises(u, p):
    raise RuntimeError("boom")

  def disconnect():
    disconnected["called"] = True

  api = DummyApi(login=login_raises, disconnect=disconnect)
  res = get_token_from_kuma_api(api, username="u", password="p")
  assert res is None
  assert disconnected["called"] is True


def test_login_raises_and_disconnect_raises_too(monkeypatch):
  def login_raises(u, p):
    raise RuntimeError("boom")

  def disconnect_raises():
    raise RuntimeError("bye")

  api = DummyApi(login=login_raises, disconnect=disconnect_raises)
  # Should not raise, just return None even if disconnect fails
  res = get_token_from_kuma_api(api, username="u", password="p")
  assert res is None
