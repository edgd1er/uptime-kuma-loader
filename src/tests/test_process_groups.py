"""
Tests for process_groups function.

These tests verify the observable behavior of process_groups:
- Return value structure and content
- Error handling for invalid inputs
- Behavior with edge cases

Each test documents:
- The behavior it protects
- The bug it would detect
- Why it doesn't depend on internal implementation details
- Why it could realistically fail

Note: We mock the API (external dependency) but verify the function's observable behavior,
not the mock calls themselves.
"""
import pytest
from unittest.mock import Mock
from typing import Dict, Any

from src.kuma_load.kuma_load import process_groups


@pytest.fixture
def mock_api():
    """Mock API - external dependency only"""
    api = Mock()
    api.add_monitor.return_value = {"monitorID": 100, "msg": "ok"}
    api.delete_monitor.return_value = {"msg": "deleted"}
    return api


# =============================================================================
# CONTRACT TESTS
# =============================================================================


def test_process_groups_api_none_raises():
    """
    CONTRACT TEST: Function validates its inputs.
    
    Behavior protected: Input validation for required api parameter
    Bug detected: Missing input validation
    No internal dependency: Only tests public interface
    Could fail: If input validation is removed or changed
    
    Test scenarios that would fail:
    1. Function doesn't check for None api
    2. Function accepts None api and crashes later
    """
    with pytest.raises(ValueError, match="api must not be None"):
        process_groups(api=None, existing_groups={}, config_groups=[], delete=False)


# =============================================================================
# UNIT TESTS - Core functionality
# =============================================================================


def test_process_groups_returns_empty_dict_when_no_config(mock_api):
    """
    UNIT TEST: Empty config produces empty result.
    
    Behavior protected: Function handles empty input correctly
    Bug detected: Logic error processing empty config
    No internal dependency: Only verifies return value
    Could fail:
    1. Function returns None instead of {}
    2. Function returns wrong type
    3. Function crashes with empty config
    
    Test scenarios that would fail:
    1. Function returns None
    2. Function returns list instead of dict
    3. Function crashes
    """
    existing = {}
    result = process_groups(
        api=mock_api,
        existing_groups=existing,
        config_groups=[],
        delete=False
    )
    assert result == {}
    assert isinstance(result, dict)


def test_process_groups_returns_original_when_empty_config(mock_api):
    """
    UNIT TEST: Empty config returns original groups unchanged.
    
    Behavior protected: Function preserves existing groups when no changes requested
    Bug detected: Function modifies existing groups unnecessarily
    No internal dependency: Only verifies return value
    Could fail: If function modifies existing_groups
    
    Test scenarios that would fail:
    1. Function returns modified dict
    2. Function returns None
    3. Function returns wrong structure
    """
    existing = {"group1": {"name": "group1", "id": 1}}
    result = process_groups(
        api=mock_api,
        existing_groups=existing,
        config_groups=[],
        delete=False
    )
    assert result == {"group1": {"name": "group1", "id": 1}}


def test_process_groups_adds_new_group_returns_correct_structure(mock_api):
    """
    UNIT TEST: Adding a new group returns correct structure.
    
    Behavior protected: Function adds new groups and returns them
    Bug detected: Function doesn't add new groups correctly
    No internal dependency: Only verifies return value, not API calls
    Could fail: If function doesn't process new groups correctly
    
    Test scenarios that would fail:
    1. Function returns empty dict
    2. Function doesn't include new_group in result
    3. Function returns wrong structure
    4. Function returns wrong id for new group
    """
    existing = {}
    config = ["new_group"]
    
    result = process_groups(
        api=mock_api,
        existing_groups=existing,
        config_groups=config,
        delete=False
    )
    
    # Verify observable behavior: result contains new group
    assert isinstance(result, dict)
    assert "new_group" in result
    assert result["new_group"]["id"] == 100  # ID from mock
    assert result["new_group"]["name"] == "new_group"


def test_process_groups_deletes_when_not_in_config_and_delete_true(mock_api):
    """
    UNIT TEST: Deleting groups not in config when delete=True.
    
    Behavior protected: Function removes old groups when delete=True
    Bug detected: Function doesn't remove old groups
    No internal dependency: Only verifies return value, not API calls
    Could fail: If function doesn't delete old groups
    
    Test scenarios that would fail:
    1. Result contains delete_me
    2. Result doesn't contain keep_me
    3. Function returns wrong structure
    """
    existing = {
        "keep_me": {"name": "keep_me", "id": 1},
        "delete_me": {"name": "delete_me", "id": 2}
    }
    config = ["keep_me"]
    
    result = process_groups(
        api=mock_api,
        existing_groups=existing,
        config_groups=config,
        delete=True
    )
    
    # Verify observable behavior: old group is deleted, new one is kept
    assert isinstance(result, dict)
    assert "keep_me" in result
    assert "delete_me" not in result


def test_process_groups_returns_dict_with_name_as_key(mock_api):
    """
    UNIT TEST: Return value is a dict with group names as keys.
    
    Behavior protected: Function returns correct structure
    Bug detected: Function returns wrong structure
    No internal dependency: Only verifies return value structure
    Could fail: If function returns wrong structure
    
    Test scenarios that would fail:
    1. Function returns list instead of dict
    2. Function uses id as key instead of name
    3. Function returns wrong type
    """
    existing = {}
    config = ["group1", "group2"]
    
    result = process_groups(
        api=mock_api,
        existing_groups=existing,
        config_groups=config,
        delete=False
    )
    
    assert isinstance(result, dict)
    assert "group1" in result
    assert "group2" in result


# =============================================================================
# NEGATIVE TESTS / REGRESSION TESTS
# =============================================================================


def test_process_groups_multiple_new_groups(mock_api):
    """
    REGRESSION TEST: Function handles multiple new groups correctly.
    
    Behavior protected: Function processes multiple additions
    Bug detected: Function only processes first group
    No internal dependency: Only verifies return value
    Could fail: If function doesn't handle multiple groups
    
    Test scenarios that would fail:
    1. Result only contains first group
    2. Function crashes with multiple groups
    3. Function returns wrong structure
    """
    existing = {}
    config = ["group_a", "group_b", "group_c"]
    
    result = process_groups(
        api=mock_api,
        existing_groups=existing,
        config_groups=config,
        delete=False
    )
    
    assert isinstance(result, dict)
    assert "group_a" in result
    assert "group_b" in result
    assert "group_c" in result


def test_process_groups_empty_existing_and_config(mock_api):
    """
    REGRESSION TEST: Function handles empty existing and config.
    
    Behavior protected: Function handles edge case correctly
    Bug detected: Function crashes with empty inputs
    No internal dependency: Only verifies return value
    Could fail: If function doesn't handle empty dict and list
    
    Test scenarios that would fail:
    1. Function crashes
    2. Function returns wrong type
    """
    result = process_groups(
        api=mock_api,
        existing_groups={},
        config_groups=[],
        delete=False
    )
    
    assert result == {}
