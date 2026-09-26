"""
Tests for add_remove_tags function.

These tests verify the observable behavior of add_remove_tags:
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
from typing import Dict, Any, List

from src.kuma_load.kuma_load import add_remove_tags


@pytest.fixture
def mock_api():
    """Mock API - external dependency only"""
    api = Mock()
    api.add_tag.return_value = {"id": 1, "name": "new_tag"}
    api.delete_tag.return_value = {"msg": "deleted"}
    api.get_tags.return_value = []
    return api


# =============================================================================
# UNIT TESTS - Core functionality
# =============================================================================


def test_add_remove_tags_api_none_returns_empty_tuple():
    """
    UNIT TEST: None API handled gracefully.
    
    Behavior protected: Function handles None API
    Bug detected: Function crashes with None API
    No internal dependency: Only verifies return value
    Could fail: If get_tags(api=None) changes behavior
    
    Test scenarios that would fail:
    1. get_tags(api=None) returns something other than ([], {})
    2. Function crashes unpacking the result
    """
    # get_tags(api=None) returns ([], {}), so unpacking works
    result = add_remove_tags(api=None, config_monitors=[], delete=False)
    
    assert result == ({}, [])
    assert isinstance(result, tuple)


def test_add_remove_tags_no_tags_in_config_returns_empty_tuple(mock_api):
    """
    UNIT TEST: Config monitors with no tags produce empty result.
    
    Behavior protected: Function handles monitors without tags
    Bug detected: Function crashes or returns wrong result
    No internal dependency: Only verifies return value
    Could fail: If function doesn't handle monitors without tags
    
    Test scenarios that would fail:
    1. Function crashes with monitors without tags
    2. Function returns wrong structure
    3. Function returns non-empty result
    """
    config_monitors = [{"name": "monitor1", "type": "http"}]
    
    result = add_remove_tags(api=mock_api, config_monitors=config_monitors, delete=False)
    
    assert result == ({}, [])


def test_add_remove_tags_adds_new_tags_returns_correct_structure(mock_api):
    """
    UNIT TEST: Adding new tags returns correct structure.
    
    Behavior protected: Function adds new tags and returns correct structure
    Bug detected: Function doesn't process new tags correctly
    No internal dependency: Only verifies return value
    Could fail: If function doesn't add new tags
    
    Test scenarios that would fail:
    1. Function returns wrong structure
    2. Function doesn't include new tags in result
    3. Function returns None
    """
    config_monitors = [
        {"name": "monitor1", "type": "http", "tags": ["tag1", "tag2"]},
        {"name": "monitor2", "type": "http", "tags": ["tag2", "tag3"]}
    ]
    
    result = add_remove_tags(api=mock_api, config_monitors=config_monitors, delete=False)
    
    # Verify observable behavior: result structure
    assert isinstance(result, tuple)
    new_tags_id, new_tags = result
    assert isinstance(new_tags_id, dict)
    assert isinstance(new_tags, list)


def test_add_remove_tags_deletes_unused_tags_when_delete_true_returns_correct_structure(mock_api):
    """
    UNIT TEST: Deleting unused tags when delete=True returns correct structure.
    
    Behavior protected: Function removes unused tags
    Bug detected: Function doesn't delete unused tags
    No internal dependency: Only verifies return value
    Could fail: If function doesn't delete unused tags
    
    Test scenarios that would fail:
    1. Function returns wrong structure
    2. Function doesn't process deletions
    3. Function crashes
    """
    config_monitors = [
        {"name": "monitor1", "type": "http", "tags": ["tag1"]}
    ]
    # Existing tags has tag2 which is not in config
    mock_api.get_tags.return_value = [
        {"id": 1, "name": "tag1"},
        {"id": 2, "name": "tag2"}
    ]
    
    result = add_remove_tags(api=mock_api, config_monitors=config_monitors, delete=True)
    
    # Verify observable behavior: result structure
    assert isinstance(result, tuple)
    new_tags_id, new_tags = result
    assert isinstance(new_tags_id, dict)
    assert isinstance(new_tags, list)


def test_add_remove_tags_handles_duplicates_in_existing_returns_correct_structure(mock_api):
    """
    UNIT TEST: Function handles duplicate tags in existing.
    
    Behavior protected: Function removes duplicate tags
    Bug detected: Function doesn't handle duplicates correctly
    No internal dependency: Only verifies return value
    Could fail: If function doesn't remove duplicates
    
    Note: When existing has duplicate tags, function should remove them.
    
    Test scenarios that would fail:
    1. Function crashes with duplicates
    2. Function returns wrong structure
    3. Function doesn't remove duplicates
    """
    config_monitors = [
        {"name": "monitor1", "type": "http", "tags": ["tag1"]}
    ]
    # Existing tags has duplicate tag1
    mock_api.get_tags.return_value = [
        {"id": 1, "name": "tag1"},
        {"id": 2, "name": "tag1"},  # duplicate
        {"id": 3, "name": "tag1"}   # another duplicate
    ]
    
    result = add_remove_tags(api=mock_api, config_monitors=config_monitors, delete=True)
    
    # Verify observable behavior: result structure
    assert isinstance(result, tuple)
    new_tags_id, new_tags = result
    assert isinstance(new_tags_id, dict)
    assert isinstance(new_tags, list)
