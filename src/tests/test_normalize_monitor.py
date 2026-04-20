import pytest
from typing import Any, Dict
from src.kuma_load.kuma_load import normalize_monitor_for_api

def test_no_http_headers_unchanged():
  m = {"name": "m1", "type": "http"}
  out = normalize_monitor_for_api(m)
  assert out == m
  assert out is not m  # shallow copy

def test_http_headers_list_of_pairs_converted():
  m = {"name": "m1", "type": "http", "http_headers": ["A=1", "B=2"]}
  out = normalize_monitor_for_api(m)
  assert out["http_headers"] == {"A": "1", "B": "2"}

def test_http_headers_list_with_spaces_and_equals_in_value():
  m = {"http_headers": ["X-Auth = token=abc==", "Y = value with spaces "]}
  out = normalize_monitor_for_api(m)
  assert out["http_headers"] == {"X-Auth": "token=abc==", "Y": "value with spaces"}

def test_http_headers_already_dict_kept():
  headers = {"A": "1"}
  m = {"http_headers": headers}
  out = normalize_monitor_for_api(m)
  assert out["http_headers"] is headers  # unchanged object
  assert out["http_headers"] == headers

def test_http_headers_ignores_malformed_entries():
  m = {"http_headers": ["noequals", 123, None, "K=V"]}
  out = normalize_monitor_for_api(m)
  assert out["http_headers"] == {"K": "V"}
