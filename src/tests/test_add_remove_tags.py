"""
Tests for add_remove_tags function.

Note: The function has bugs:
1. Does not handle config_monitors=None (will raise TypeError)
2. Does not handle api=None properly in all code paths
"""
import pytest
from unittest.mock import Mock
from typing import Dict, Any, List

from src.kuma_load.kuma_load import add_remove_tags


@pytest.fixture
def mock_api():
    """Create a mock API for testing"""
    api = Mock()
    api.add_tag = Mock()
    api.delete_tag = Mock()
    api.get_tags = Mock()
    return api


def test_add_remove_tags_api_none():
    """Test with None API raises ValueError due to bug in get_tags
    
    Note: get_tags(api=None) returns [] instead of ([], {})
    This causes unpacking error in add_remove_tags when it does:
    existing_tags, existing_tags_id = get_tags(api)
    """
    # This will raise ValueError because get_tags returns [] but we expect 2 values
    with pytest.raises(ValueError) as exc:
        add_remove_tags(api=None, config_monitors=[], delete=False)
    
    assert "not enough values to unpack" in str(exc.value)


def test_add_remove_tags_no_tags_in_config(mock_api):
    """Test when config monitors have no tags"""
    config_monitors = [{"name": "monitor1", "type": "http"}]
    mock_api.get_tags.return_value = []
    
    result = add_remove_tags(api=mock_api, config_monitors=config_monitors, delete=False)
    
    # Should return empty tags
    assert result == ({}, [])


def test_add_remove_tags_adds_new_tags(mock_api):
    """Test adding new tags from config"""
    config_monitors = [
        {"name": "monitor1", "type": "http", "tags": ["tag1", "tag2"]},
        {"name": "monitor2", "type": "http", "tags": ["tag2", "tag3"]}
    ]
    # Existing tags is empty
    mock_api.get_tags.return_value = []
    
    # Mock add_tag to return a tag with id
    mock_api.add_tag.return_value = {"id": 1, "name": "tag1"}
    
    result = add_remove_tags(api=mock_api, config_monitors=config_monitors, delete=False)
    
    # Should have called add_tag for new tags
    # config_tags = ["tag1", "tag2", "tag2", "tag3"] -> unique: ["tag1", "tag2", "tag3"]
    assert mock_api.add_tag.call_count == 3
    
    # Result should contain the new tags
    assert isinstance(result, tuple)
    new_tags_id, new_tags = result
    assert isinstance(new_tags_id, dict)
    assert isinstance(new_tags, list)


def test_add_remove_tags_deletes_unused_tags_when_delete_true(mock_api):
    """Test that unused tags are deleted when delete=True"""
    config_monitors = [
        {"name": "monitor1", "type": "http", "tags": ["tag1"]}
    ]
    # Existing tags has tag2 which is not in config
    mock_api.get_tags.return_value = [
        {"id": 1, "name": "tag1"},
        {"id": 2, "name": "tag2"}
    ]
    
    # Mock delete_tag
    mock_api.delete_tag.return_value = {"msg": "deleted"}
    
    result = add_remove_tags(api=mock_api, config_monitors=config_monitors, delete=True)
    
    # Should have called delete_tag for tag2
    mock_api.delete_tag.assert_called_once()
    call_kwargs = mock_api.delete_tag.call_args[1]
    assert call_kwargs["id_"] == 2


def test_add_remove_tags_handles_duplicates_in_existing(mock_api):
    """Test that duplicate tags in existing are removed when delete=True"""
    config_monitors = [
        {"name": "monitor1", "type": "http", "tags": ["tag1"]}
    ]
    # Existing tags has duplicate tag1
    mock_api.get_tags.return_value = [
        {"id": 1, "name": "tag1"},
        {"id": 2, "name": "tag1"},  # duplicate
        {"id": 3, "name": "tag1"}   # another duplicate
    ]
    
    # Mock delete_tag
    mock_api.delete_tag.return_value = {"msg": "deleted"}
    
    result = add_remove_tags(api=mock_api, config_monitors=config_monitors, delete=True)
    
    # Should have called delete_tag for duplicates (2 times for the extra duplicates)
    # The function removes duplicates by deleting v-1 times for each duplicate
    # Counter will have tag1: 3, so duplicates = {tag1: 3}
    # It will delete 2 times (v-1 = 2)
    assert mock_api.delete_tag.call_count == 2
