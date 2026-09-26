"""
Tests for process_notifications function.

Note: The function has a bug where it returns {n['name']: n for n in existing_notifications}
where existing_notifications is the original input parameter, not the updated dict.
This means changes (adds, deletes) are not reflected in the return value.
This is documented in the bug report.

Also, the function expects API methods to return dicts with 'id' and 'msg' keys.
"""
import pytest
from unittest.mock import Mock
from typing import Dict, Any

from src.kuma_load.kuma_load import process_notifications


def make_notification(name: str, notification_id: int = None) -> Dict[str, Any]:
    """Create a notification dict for testing"""
    notif = {"name": name}
    if notification_id:
        notif["id"] = notification_id
    return notif


@pytest.fixture
def mock_api():
    """Create a mock API for testing"""
    api = Mock()
    api.add_notification = Mock()
    api.edit_notification = Mock()
    api.delete_notification = Mock()
    return api


def test_process_notifications_returns_empty_dict_when_no_config():
    """Test with empty config returns empty dict"""
    api = Mock()
    # Pass empty list to avoid TypeError with None
    result = process_notifications(
        api=api,
        existing_notifications=[],
        config_notifications=[],
        delete=False
    )
    # Bug: Returns {n['name']: n for n in existing_notifications} where existing_notifications is []
    assert result == {}


def test_process_notifications_returns_original_existing_when_empty_config():
    """Test with empty config returns original existing notifications as dict"""
    api = Mock()
    existing = [{"name": "existing", "id": 1}]
    result = process_notifications(
        api=api,
        existing_notifications=existing,
        config_notifications=[],
        delete=False
    )
    # Bug: Returns {n['name']: n for n in existing_notifications} = {"existing": {"name": "existing", "id": 1}}
    assert result == {"existing": {"name": "existing", "id": 1}}


def test_process_notifications_calls_add_for_new_notification():
    """Test that add_notification is called for new notifications"""
    api = Mock()
    existing = []
    config = [{"name": "new_notif", "type": "discord"}]
    
    # Mock must return a dict with 'id' and 'msg' keys
    api.add_notification.return_value = {"id": 100, "msg": "ok"}
    
    # Bug: The function will add to existing_notifications_dict but return is based on original existing
    result = process_notifications(
        api=api,
        existing_notifications=existing,
        config_notifications=config,
        delete=False
    )
    
    # Should have called add_notification with correct args
    api.add_notification.assert_called_once()
    call_kwargs = api.add_notification.call_args[1]
    assert call_kwargs["name"] == "new_notif"
    assert call_kwargs["type"] == "discord"
    
    # Bug: result is based on original existing (which is empty), so result is empty
    assert result == {}


def test_process_notifications_calls_edit_for_existing_notification():
    """Test that edit_notification is called for existing notifications"""
    api = Mock()
    existing = [{"name": "existing_notif", "id": 1, "type": "email"}]
    config = [{"name": "existing_notif", "type": "discord"}]
    
    # Mock must return a dict with 'id' and 'msg' keys
    api.edit_notification.return_value = {"id": 1, "msg": "edited"}
    
    result = process_notifications(
        api=api,
        existing_notifications=existing,
        config_notifications=config,
        delete=False
    )
    
    # Should have called edit_notification, not add
    api.edit_notification.assert_called_once()
    api.add_notification.assert_not_called()
    
    # Check the call arguments - should have id_ parameter
    call_kwargs = api.edit_notification.call_args[1]
    assert call_kwargs["id_"] == 1
    assert call_kwargs["type"] == "discord"
    
    # Bug: result is based on original existing
    assert "existing_notif" in result


def test_process_notifications_calls_delete_when_not_in_config_and_delete_true():
    """Test that delete_notification is called when delete=True"""
    api = Mock()
    existing = [
        {"name": "keep_me", "id": 1},
        {"name": "delete_me", "id": 2}
    ]
    config = [{"name": "keep_me"}]
    
    # Mock must return a dict with 'msg' key
    api.delete_notification.return_value = {"msg": "deleted"}
    # edit_notification will be called for keep_me (to_edit), must also return dict
    api.edit_notification.return_value = {"id": 1, "msg": "edited"}
    
    result = process_notifications(
        api=api,
        existing_notifications=existing,
        config_notifications=config,
        delete=True
    )
    
    # Should have deleted the notification not in config
    api.delete_notification.assert_called_once()
    call_kwargs = api.delete_notification.call_args[1]
    assert call_kwargs["id_"] == 2
    
    # Should have edited keep_me
    api.edit_notification.assert_called_once()
    
    # Bug: result is based on original existing, so both are still there
    assert "keep_me" in result
    assert "delete_me" in result


def test_process_notifications_handles_duplicates_in_existing():
    """Test that duplicate notifications in existing are added to to_delete set"""
    # Note: When creating existing_notifications_dict from existing, duplicate names 
    # will be overwritten (only last one kept)
    api = Mock()
    existing = [
        {"name": "dup_notif", "id": 1},
        {"name": "dup_notif", "id": 2},  # This overwrites the first in the dict
        {"name": "keep_me", "id": 3}
    ]
    config = [{"name": "keep_me"}]
    
    # Mock must return a dict with 'msg' key
    api.delete_notification.return_value = {"msg": "deleted"}
    # edit_notification will be called for keep_me (to_edit), must also return dict
    api.edit_notification.return_value = {"id": 3, "msg": "edited"}
    
    result = process_notifications(
        api=api,
        existing_notifications=existing,
        config_notifications=config,
        delete=True
    )
    
    # The function adds duplicates to to_delete set using Counter on existing_notifications_names
    # which comes from [e['name'] for e in existing] = ["dup_notif", "dup_notif", "keep_me"]
    # So Counter will have dup_notif: 2, and it will be added to to_delete
    # So delete should be called
    assert api.delete_notification.call_count >= 1
    
    # Bug: result is based on original existing
    assert "keep_me" in result
    assert "dup_notif" in result


def test_process_notifications_return_type_is_dict():
    """Test that the return value is always a dict"""
    api = Mock()
    existing = [
        {"name": "notif1", "id": 1},
        {"name": "notif2", "id": 2}
    ]
    config = [{"name": "notif1"}]
    
    # Mock must return a dict with 'msg' key
    api.edit_notification.return_value = {"id": 1, "msg": "edited"}
    
    result = process_notifications(
        api=api,
        existing_notifications=existing,
        config_notifications=config,
        delete=False
    )
    
    # Result should be a dict
    assert isinstance(result, dict)
    assert "notif1" in result
    assert "notif2" in result
