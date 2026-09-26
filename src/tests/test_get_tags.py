"""
Tests for get_tags function.

These tests verify the observable behavior of get_tags:
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

from src.kuma_load.kuma_load import get_tags, DataFetchError


# =============================================================================
# UNIT TESTS - Core functionality
# =============================================================================


def test_get_tags_api_none():
    """
    UNIT TEST: None API returns empty tuple.
    
    Behavior protected: Function handles None API gracefully
    Bug detected: Function crashes with None API
    No internal dependency: Only verifies return value
    Could fail: If function doesn't handle None API
    
    Test scenarios that would fail:
    1. Function crashes with AttributeError
    2. Function returns wrong type
    3. Function returns wrong structure
    """
    result = get_tags(None)
    # Returns tuple of empty lists when api is None
    assert result == ([], {})
    assert isinstance(result, tuple)
    assert len(result) == 2


def test_get_tags_empty_list(caplog):
    """
    UNIT TEST: Empty API response produces empty results.
    
    Behavior protected: Function handles empty API response correctly
    Bug detected: Logic error processing empty response
    No internal dependency: Verifies return values and logging
    Could fail: If function doesn't handle empty list
    
    Test scenarios that would fail:
    1. Function crashes with empty list
    2. Function returns wrong structure
    3. Function doesn't log correctly
    """
    api = Mock()
    api.get_tags.return_value = []

    caplog.set_level(logging.INFO)
    existing_tags, existing_tags_id = get_tags(api)

    assert existing_tags == []
    assert existing_tags_id == {}

    # Verify logs
    assert any("existing_tags: 0" in r.getMessage() for r in caplog.records)


def test_get_tags_with_tags(caplog):
    """
    UNIT TEST: Function correctly processes tags from API.
    
    Behavior protected: Function processes tags and creates ID mapping
    Bug detected: Function loses or incorrectly processes tags
    No internal dependency: Only verifies return values and logging
    Could fail: If function doesn't process tags correctly
    
    Test scenarios that would fail:
    1. Function doesn't create correct existing_tags_id mapping
    2. Function returns wrong structure
    3. Function doesn't extract names correctly
    4. Function doesn't log debug info
    """
    api = Mock()
    sample = [
        {"id": 1, "name": "alpha", "other": "x"},
        {"id": 2, "name": "beta", "other": "y"},
    ]
    api.get_tags.return_value = sample

    caplog.set_level(logging.DEBUG)
    existing_tags, existing_tags_id = get_tags(api)

    # Base verifications
    assert existing_tags == sample
    # existing_tags_id should be a dict mapping id -> tag dict
    assert isinstance(existing_tags_id, dict)
    assert existing_tags_id[1]["name"] == "alpha"
    assert existing_tags_id[2]["name"] == "beta"
    # Verify extracted names
    names = [t["name"] for t in existing_tags]
    assert names == ["alpha", "beta"]

    # Verify debug log contains tag names
    assert any("alpha" in r.getMessage() and "beta" in r.getMessage() for r in caplog.records)


# =============================================================================
# ERROR HANDLING TESTS
# =============================================================================


def test_get_tags_api_exception_raises_datafetcherror(caplog):
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
    api.get_tags.side_effect = RuntimeError("boom")

    caplog.set_level(logging.ERROR)
    with pytest.raises(DataFetchError) as excinfo:
        get_tags(api)

    # Verify error was logged
    assert any("Failed to get existing tags" in r.message for r in caplog.records)
