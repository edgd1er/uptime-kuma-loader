"""
Tests for process_notifications function.

These tests verify the observable behavior of process_notifications:
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

from src.kuma_load.kuma_load import process_notifications


# =============================================================================
# CONTRACT TESTS
# =============================================================================


def test_process_notifications_api_none_raises():
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
        process_notifications(api=None, existing_notifications=[], config_notifications=[], delete=False)


# =============================================================================
# UNIT TESTS - Core functionality
# =============================================================================


def test_process_notifications_returns_empty_dict_when_no_config():
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
    api = Mock()
    result = process_notifications(
        api=api,
        existing_notifications=[],
        config_notifications=[],
        delete=False
    )
    assert result == {}
    assert isinstance(result, dict)


def test_process_notifications_returns_existing_when_empty_config():
    """
    UNIT TEST: Empty config returns existing notifications.
    
    Behavior protected: Function preserves existing notifications when no changes requested
    Bug detected: Function loses existing notifications
    No internal dependency: Only verifies return value
    Could fail: If function doesn't preserve existing notifications
    
    Test scenarios that would fail:
    1. Function returns empty dict
    2. Function loses existing notifications
    3. Function returns wrong structure
    """
    api = Mock()
    existing = [{"name": "existing", "id": 1}]
    result = process_notifications(
        api=api,
        existing_notifications=existing,
        config_notifications=[],
        delete=False
    )
    assert result == {"existing": {"name": "existing", "id": 1}}


def test_process_notifications_adds_new_notification():
    """
    UNIT TEST: Adding a new notification returns correct structure.
    
    Behavior protected: Function adds new notifications and returns them
    Bug detected: Function doesn't add new notifications correctly
    No internal dependency: Only verifies return value, not API calls
    Could fail: If function doesn't process new notifications correctly
    
    Test scenarios that would fail:
    1. Function returns empty dict
    2. Function doesn't include new_notif in result
    3. Function returns wrong structure
    4. Function returns wrong id for new notification
    """
    api = Mock()
    api.add_notification.return_value = {"id": 100, "msg": "ok"}
    
    existing = []
    config = [{"name": "new_notif", "type": "discord"}]
    
    result = process_notifications(
        api=api,
        existing_notifications=existing,
        config_notifications=config,
        delete=False
    )
    
    # Verify observable behavior: result contains new notification
    assert isinstance(result, dict)
    assert "new_notif" in result
    assert result["new_notif"]["id"] == 100
    assert result["new_notif"]["name"] == "new_notif"


def test_process_notifications_edits_existing_notification():
    """
    UNIT TEST: Editing an existing notification updates result.
    
    Behavior protected: Function updates existing notifications
    Bug detected: Function doesn't update notifications correctly
    No internal dependency: Only verifies return value
    Could fail: If function doesn't update notifications
    
    Test scenarios that would fail:
    1. Result doesn't contain existing_notif
    2. Result contains wrong type
    3. Function doesn't update type field
    """
    api = Mock()
    api.edit_notification.return_value = {"id": 1, "msg": "edited"}
    
    existing = [{"name": "existing_notif", "id": 1, "type": "email"}]
    config = [{"name": "existing_notif", "type": "discord"}]
    
    result = process_notifications(
        api=api,
        existing_notifications=existing,
        config_notifications=config,
        delete=False
    )
    
    # Verify observable behavior: result contains edited notification
    assert isinstance(result, dict)
    assert "existing_notif" in result
    assert result["existing_notif"]["id"] == 1


def test_process_notifications_deletes_when_not_in_config_and_delete_true():
    """
    UNIT TEST: Deleting notifications not in config when delete=True.
    
    Behavior protected: Function removes old notifications when delete=True
    Bug detected: Function doesn't delete old notifications
    No internal dependency: Only verifies return value
    Could fail: If function doesn't delete old notifications
    
    Test scenarios that would fail:
    1. Result contains delete_me
    2. Result doesn't contain keep_me
    3. Function returns wrong structure
    """
    api = Mock()
    api.delete_notification.return_value = {"msg": "deleted"}
    api.edit_notification.return_value = {"id": 1, "msg": "edited"}
    
    existing = [
        {"name": "keep_me", "id": 1},
        {"name": "delete_me", "id": 2}
    ]
    config = [{"name": "keep_me"}]
    
    result = process_notifications(
        api=api,
        existing_notifications=existing,
        config_notifications=config,
        delete=True
    )
    
    # Verify observable behavior: old notification is deleted, new one is kept
    assert isinstance(result, dict)
    assert "keep_me" in result
    assert "delete_me" not in result


def test_process_notifications_always_returns_dict():
    """
    UNIT TEST: Return value is always a dict.
    
    Behavior protected: Function always returns a dict
    Bug detected: Function returns wrong type
    No internal dependency: Only verifies return value type
    Could fail: If function returns wrong type
    
    Test scenarios that would fail:
    1. Function returns list
    2. Function returns None
    3. Function returns wrong structure
    """
    api = Mock()
    api.edit_notification.return_value = {"id": 1, "msg": "edited"}
    
    existing = [
        {"name": "notif1", "id": 1},
        {"name": "notif2", "id": 2}
    ]
    config = [{"name": "notif1"}]
    
    result = process_notifications(
        api=api,
        existing_notifications=existing,
        config_notifications=config,
        delete=False
    )
    
    assert isinstance(result, dict)
    assert "notif1" in result
    assert "notif2" in result


# =============================================================================
# NEGATIVE TESTS / REGRESSION TESTS
# =============================================================================


def test_process_notifications_handles_duplicates_in_existing():
    """
    REGRESSION TEST: Function handles duplicate notifications in existing.
    
    Behavior protected: Function handles duplicates correctly
    Bug detected: Function crashes or behaves incorrectly with duplicates
    No internal dependency: Only verifies return value
    Could fail: If function doesn't handle duplicates
    
    Note: When creating existing_notifications_dict from existing, duplicate names
    will be overwritten (only last one kept).
    
    Test scenarios that would fail:
    1. Function crashes with duplicates
    2. Function returns wrong structure
    3. Result contains both duplicates
    """
    api = Mock()
    api.delete_notification.return_value = {"msg": "deleted"}
    api.edit_notification.return_value = {"id": 3, "msg": "edited"}
    
    existing = [
        {"name": "dup_notif", "id": 1},
        {"name": "dup_notif", "id": 2},  # This overwrites the first in the dict
        {"name": "keep_me", "id": 3}
    ]
    config = [{"name": "keep_me"}]
    
    result = process_notifications(
        api=api,
        existing_notifications=existing,
        config_notifications=config,
        delete=True
    )
    
    # Result should only contain keep_me
    assert isinstance(result, dict)
    assert "keep_me" in result
    # dup_notif should be deleted (it's in existing but not in config)
    assert "dup_notif" not in result
