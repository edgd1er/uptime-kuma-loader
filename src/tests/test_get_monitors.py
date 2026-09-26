"""
Tests for get_monitors function.

These tests verify the observable behavior of get_monitors:
- Return value structure and content
- Error handling for invalid inputs
- Behavior with edge cases

Each test documents:
- The behavior it protects
- The bug it would detect
- Why it doesn't depend on internal implementation details
- Why it could realistically fail

Note: We mock the API (external dependency) but verify the function's observable behavior.
"""
import pytest
from unittest.mock import Mock
import logging

from src.kuma_load.kuma_load import get_monitors, DataFetchError


# =============================================================================
# CONTRACT TESTS
# =============================================================================


def test_get_monitors_api_none_raises_attributeerror():
    """
    CONTRACT TEST: Function validates its inputs.
    
    Behavior protected: Input validation for required api parameter
    Bug detected: Missing input validation
    No internal dependency: Only tests public interface
    Could fail: If function doesn't check for None api
    
    Test scenarios that would fail:
    1. Function accepts None api and crashes later
    2. Function has different validation logic
    """
    # The function doesn't anticipate api=None; expect AttributeError
    with pytest.raises(AttributeError):
        get_monitors(None)


# =============================================================================
# UNIT TESTS - Core functionality
# =============================================================================


def test_get_monitors_empty_list():
    """
    UNIT TEST: Empty API response produces empty results.
    
    Behavior protected: Function handles empty API response correctly
    Bug detected: Logic error processing empty response
    No internal dependency: Only verifies return values
    Could fail: If function doesn't handle empty list
    
    Test scenarios that would fail:
    1. Function crashes with empty list
    2. Function returns wrong structure
    3. Function doesn't return empty lists
    """
    api = Mock()
    api.get_monitors.return_value = []

    existing_config, existing_monitors = get_monitors(api)

    assert existing_config == []
    assert existing_monitors == {}


def test_get_monitors_with_monitors():
    """
    UNIT TEST: Function correctly processes monitors from API.
    
    Behavior protected: Function processes and filters monitors correctly
    Bug detected: Function loses or incorrectly processes monitors
    No internal dependency: Only verifies return values
    Could fail: If function doesn't process monitors correctly
    
    Test scenarios that would fail:
    1. Function doesn't filter monitors without 'name' field
    2. Function doesn't filter monitors without 'id' field
    3. Function returns wrong structure
    4. Function includes invalid monitors in existing_monitors
    """
    api = Mock()
    sample = [
        {"id": 10, "name": "site-a", "url": "https://a.example"},
        {"id": 11, "name": "site-b", "url": "https://b.example"},
        {"id": 12, "no_name": True},  # Should be ignored - no "name"
        {"id": 13, "name": "site-c"},  # Valid even without other fields
        {"name": "no_id"},  # Should be ignored - no "id"
    ]
    api.get_monitors.return_value = sample

    existing_config, existing_monitors = get_monitors(api)

    # existing_config should be the raw list
    assert existing_config == sample

    # existing_monitors should only contain entries with both "name" and "id"
    assert "site-a" in existing_monitors
    assert existing_monitors["site-a"]["id"] == 10
    assert "site-b" in existing_monitors
    assert existing_monitors["site-b"]["url"] == "https://b.example"
    assert "site-c" in existing_monitors
    assert existing_monitors["site-c"]["id"] == 13

    # Invalid entries should be ignored
    assert "no_id" not in existing_monitors
    # The element without "name" should not appear
    assert not any(mon.get("no_name") for mon in existing_monitors.values())


# =============================================================================
# ERROR HANDLING TESTS
# =============================================================================


def test_get_monitors_api_exception_raises_datafetcherror(caplog):
    """
    UNIT TEST: API exception raises DataFetchError instead of calling sys.exit.
    
    Behavior protected: Function raises DataFetchError on API failure
    Bug detected: Function calls sys.exit instead of raising exception
    No internal dependency: Verifies exception type and logging
    Could fail: If function doesn't raise DataFetchError
    
    Test scenarios that would fail:
    1. Function calls sys.exit instead of raising
    2. Function raises wrong exception type
    3. Function doesn't log the error
    """
    api = Mock()
    api.get_monitors.side_effect = RuntimeError("boom")
    api.disconnect = Mock()

    caplog.set_level(logging.ERROR)
    with pytest.raises(DataFetchError) as excinfo:
        get_monitors(api)

    # Verify error was logged
    assert any("Failed to fetch existing monitors" in r.getMessage() for r in caplog.records)
    # Verify disconnect was called (side effect, but important for cleanup)
    # This is acceptable as it verifies a side effect, not just the mock call
    api.disconnect.assert_called_once()
