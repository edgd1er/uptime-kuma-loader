"""
Tests for process_groups function.

Note: The function has similar behavior to process_notifications.
It modifies existing_groups dict but returns it.
"""
import pytest
from unittest.mock import Mock
from typing import Dict, Any

from src.kuma_load.kuma_load import process_groups


@pytest.fixture
def mock_api():
    """Create a mock API for testing"""
    api = Mock()
    api.add_monitor = Mock()
    api.delete_monitor = Mock()
    return api


def test_process_groups_returns_empty_dict_when_no_config():
    """Test with empty config returns empty dict"""
    api = Mock()
    existing = {}
    result = process_groups(
        api=api,
        existing_groups=existing,
        config_groups=[],
        delete=False
    )
    assert result == {}


def test_process_groups_returns_original_when_empty_config():
    """Test with empty config returns original groups"""
    api = Mock()
    existing = {"group1": {"name": "group1", "id": 1}}
    result = process_groups(
        api=api,
        existing_groups=existing,
        config_groups=[],
        delete=False
    )
    # Bug: Returns existing_groups which is modified
    assert result == {"group1": {"name": "group1", "id": 1}}


def test_process_groups_adds_new_group(mock_api):
    """Test adding a new group that doesn't exist"""
    existing = {}
    config = ["new_group"]
    
    # Mock must return a dict with 'monitorID' key
    mock_api.add_monitor.return_value = {"monitorID": 100, "msg": "ok"}
    
    result = process_groups(
        api=mock_api,
        existing_groups=existing,
        config_groups=config,
        delete=False
    )
    
    # Should have called add_monitor
    mock_api.add_monitor.assert_called_once()
    call_kwargs = mock_api.add_monitor.call_args[1]
    assert call_kwargs["name"] == "new_group"
    assert call_kwargs["type"] == "group"
    
    # Result should contain the new group
    assert "new_group" in result
    assert result["new_group"]["id"] == 100


def test_process_groups_deletes_when_not_in_config_and_delete_true(mock_api):
    """Test deleting groups not in config when delete=True"""
    existing = {
        "keep_me": {"name": "keep_me", "id": 1},
        "delete_me": {"name": "delete_me", "id": 2}
    }
    config = ["keep_me"]
    
    # Mock must return a dict with 'msg' key
    mock_api.delete_monitor.return_value = {"msg": "deleted"}
    
    result = process_groups(
        api=mock_api,
        existing_groups=existing,
        config_groups=config,
        delete=True
    )
    
    # Should have deleted the group not in config
    mock_api.delete_monitor.assert_called_once()
    call_kwargs = mock_api.delete_monitor.call_args[1]
    assert call_kwargs["id_"] == 2
    
    # Result should not contain deleted group
    assert "keep_me" in result
    assert "delete_me" not in result


def test_process_groups_returns_dict_with_name_as_key(mock_api):
    """Test that the return value is a dict with group names as keys"""
    existing = {}
    config = ["group1", "group2"]
    
    mock_api.add_monitor.side_effect = [
        {"monitorID": 1, "msg": "ok"},
        {"monitorID": 2, "msg": "ok"}
    ]
    
    result = process_groups(
        api=mock_api,
        existing_groups=existing,
        config_groups=config,
        delete=False
    )
    
    # Result should be a dict with name as key
    assert isinstance(result, dict)
    assert "group1" in result
    assert "group2" in result
