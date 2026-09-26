"""
Tests for update_monitor_tags function.

These tests verify the observable behavior of update_monitor_tags:
- API calls made (as side effects)
- Error handling and logging
- Function contract (parameters, return value)

Each test documents:
- The behavior it protects
- The bug it would detect
- Why it doesn't depend on internal implementation details
- Why it could realistically fail

Note: Since this function returns None, we verify observable behavior through:
- API calls made (side effects that can be verified)
- Exceptions raised
- Log messages
"""
import pytest
from unittest.mock import Mock
from typing import Dict, Any

from src.kuma_load.kuma_load import update_monitor_tags


@pytest.fixture
def mock_api():
    """Mock API - external dependency only"""
    api = Mock()
    api.add_monitor_tag.return_value = {"msg": "Tag added"}
    api.delete_monitor_tag.return_value = {"msg": "Tag deleted"}
    return api


@pytest.fixture
def sample_existing_tags():
    """Representative existing tags data"""
    return {
        "tag1": {"id": 1, "name": "tag1", "color": "#FF0000"},
        "tag2": {"id": 2, "name": "tag2", "color": "#00FF00"},
        "tag3": {"id": 3, "name": "tag3", "color": "#0000FF"}
    }


@pytest.fixture
def sample_kuma_monitor():
    """Representative kuma monitor with tags"""
    return {
        "id": 100,
        "name": "test-monitor",
        "tags": [
            {"tag_id": 1, "tag_name": "tag1"},
            {"tag_id": 2, "tag_name": "tag2"}
        ]
    }


# Helper fixtures for specific test cases
@pytest.fixture
def empty_kuma_monitor():
    """Kuma monitor with no tags"""
    return {"id": 100, "name": "test", "tags": []}


@pytest.fixture
def kuma_monitor_without_tag_id():
    """Kuma monitor with tags missing 'tag_id' key"""
    return {
        "id": 100,
        "name": "test-monitor",
        "tags": [
            {"tag_name": "tag1"},  # Missing 'tag_id' key
        ]
    }


# =============================================================================
# CONTRACT TESTS
# =============================================================================


def test_update_monitor_tags_none_api_returns_early():
    """
    CONTRACT TEST: Function handles None API gracefully.
    
    Behavior protected: Function validates inputs and returns early
    Bug detected: Function crashes with None API
    No internal dependency: Only verifies no crash
    Could fail: If input validation is broken
    
    Test scenarios that would fail:
    1. Function crashes with None API
    2. Function tries to use None API
    """
    monitor = {"name": "test", "tags": ["tag1"]}
    kuma_monitor = {"id": 100, "name": "test-monitor", "tags": []}
    existing_tags = {"tag1": {"id": 1, "name": "tag1"}}
    
    update_monitor_tags(
        api=None,
        monitor_id=100,
        monitor=monitor,
        kuma_monitor=kuma_monitor,
        existing_tags=existing_tags,
        delete=False
    )
    # Should return without crashing


def test_update_monitor_tags_none_monitor_returns_early():
    """
    CONTRACT TEST: Function handles None monitor gracefully.
    
    Behavior protected: Function validates inputs and returns early
    Bug detected: Function crashes with None monitor
    No internal dependency: Only verifies no crash
    Could fail: If input validation is broken
    """
    kuma_monitor = {"id": 100, "name": "test-monitor", "tags": []}
    existing_tags = {"tag1": {"id": 1, "name": "tag1"}}
    
    update_monitor_tags(
        api=Mock(),
        monitor_id=100,
        monitor=None,
        kuma_monitor=kuma_monitor,
        existing_tags=existing_tags,
        delete=False
    )
    # Should return without crashing


def test_update_monitor_tags_none_existing_tags_returns_early():
    """
    CONTRACT TEST: Function handles None existing_tags gracefully.
    
    Behavior protected: Function validates inputs and returns early
    Bug detected: Function crashes with None existing_tags
    No internal dependency: Only verifies no crash
    Could fail: If input validation is broken
    """
    monitor = {"name": "test", "tags": ["tag1"]}
    kuma_monitor = {"id": 100, "name": "test-monitor", "tags": []}
    
    update_monitor_tags(
        api=Mock(),
        monitor_id=100,
        monitor=monitor,
        kuma_monitor=kuma_monitor,
        existing_tags=None,
        delete=False
    )
    # Should return without crashing


# =============================================================================
# BEHAVIOR TESTS - Verify through API side effects
# =============================================================================


def test_update_monitor_tags_monitor_id_zero_returns_early(mock_api):
    """
    BEHAVIOR TEST: Function returns early when monitor_id is 0.
    
    Behavior protected: Function handles edge case of monitor_id=0
    Bug detected: 
    - **BUG**: Function checks `monitor_id == 0` but 0 could be a valid ID
    - Function should allow 0 as a valid ID
    No internal dependency: Verifies API side effects
    Could fail: If validation logic is changed
    
    Test scenarios that would fail:
    1. Function doesn't check monitor_id
    2. Function allows monitor_id=0 (would be better)
    3. Function crashes
    """
    monitor = {"name": "test", "tags": ["tag1"]}
    kuma_monitor = {"id": 100, "name": "test-monitor", "tags": []}
    existing_tags = {"tag1": {"id": 1, "name": "tag1"}}
    
    update_monitor_tags(
        api=mock_api,
        monitor_id=0,  # This will cause early return - bug in original code
        monitor=monitor,
        kuma_monitor=kuma_monitor,
        existing_tags=existing_tags,
        delete=False
    )
    
    # Due to the bug, this will return early without calling API
    assert mock_api.add_monitor_tag.call_count == 0


def test_update_monitor_tags_monitor_id_none_returns_early(mock_api):
    """
    BEHAVIOR TEST: Function returns early when monitor_id is None.
    
    Behavior protected: Function handles None monitor_id
    Bug detected: Function crashes with None monitor_id
    No internal dependency: Verifies API side effects
    Could fail: If validation logic is broken
    """
    monitor = {"name": "test", "tags": ["tag1"]}
    kuma_monitor = {"id": 100, "name": "test-monitor", "tags": []}
    existing_tags = {"tag1": {"id": 1, "name": "tag1"}}
    
    update_monitor_tags(
        api=mock_api,
        monitor_id=None,
        monitor=monitor,
        kuma_monitor=kuma_monitor,
        existing_tags=existing_tags,
        delete=False
    )
    
    assert mock_api.add_monitor_tag.call_count == 0


def test_update_monitor_tags_adds_new_tags(mock_api):
    """
    BEHAVIOR TEST: Function adds new tags to monitor.
    
    Behavior protected: Function adds tags from config that don't exist in kuma_monitor
    Bug detected: Function doesn't add new tags
    No internal dependency: Verifies API side effects
    Could fail: If tag addition logic is broken
    
    Test scenarios that would fail:
    1. Function doesn't add tag3
    2. Function adds wrong tag ID
    3. Function doesn't call API
    """
    monitor = {"name": "test", "tags": ["tag3"]}
    existing_tags = {"tag1": {"id": 1}, "tag2": {"id": 2}, "tag3": {"id": 3}}
    
    update_monitor_tags(
        api=mock_api,
        monitor_id=100,
        monitor=monitor,
        kuma_monitor={"id": 100, "name": "test", "tags": []},  # No existing tags
        existing_tags=existing_tags,
        delete=False
    )
    
    # Verify observable side effect: add_monitor_tag was called
    assert mock_api.add_monitor_tag.call_count == 1
    call_kwargs = mock_api.add_monitor_tag.call_args[1]
    assert call_kwargs["tag_id"] == 3
    assert call_kwargs["monitor_id"] == 100


def test_update_monitor_tags_skips_existing_tags(mock_api, sample_kuma_monitor, sample_existing_tags):
    """
    BEHAVIOR TEST: Function skips tags that already exist in kuma_monitor.
    
    Behavior protected: Function doesn't re-add existing tags
    Bug detected: Function re-adds tags that already exist
    No internal dependency: Verifies API side effects
    Could fail: If duplicate check is broken
    
    Test scenarios that would fail:
    1. Function adds tag1 even though it exists
    2. Function doesn't check for existing tags
    3. Function adds wrong tags
    """
    # monitor has tag1, which kuma_monitor already has
    monitor = {"name": "test", "tags": ["tag1"]}
    
    update_monitor_tags(
        api=mock_api,
        monitor_id=100,
        monitor=monitor,
        kuma_monitor=sample_kuma_monitor,
        existing_tags=sample_existing_tags,
        delete=False
    )
    
    # Should NOT add tag1 since it's already in kuma_monitor
    assert mock_api.add_monitor_tag.call_count == 0


def test_update_monitor_tags_deletes_tags_when_delete_true(mock_api, sample_kuma_monitor, sample_existing_tags):
    """
    BEHAVIOR TEST: Function deletes tags when delete=True and they're not in config.
    
    Behavior protected: Function removes tags not in config
    Bug detected: Function doesn't delete old tags
    No internal dependency: Verifies API side effects
    Could fail: If deletion logic is broken
    
    Test scenarios that would fail:
    1. Function doesn't delete tags
    2. Function deletes wrong tags
    3. Function deletes all tags
    """
    # monitor has no tags, but kuma_monitor has tag1 and tag2
    monitor = {"name": "test", "tags": []}
    
    update_monitor_tags(
        api=mock_api,
        monitor_id=100,
        monitor=monitor,
        kuma_monitor=sample_kuma_monitor,
        existing_tags=sample_existing_tags,
        delete=True
    )
    
    # Should delete both tags from kuma_monitor
    assert mock_api.delete_monitor_tag.call_count == 2
    
    # Verify both tag_ids (1 and 2) were passed
    calls = mock_api.delete_monitor_tag.call_args_list
    tag_ids = [call[1]["tag_id"] for call in calls]
    assert set(tag_ids) == {1, 2}


def test_update_monitor_tags_multiple_new_tags(mock_api):
    """
    BEHAVIOR TEST: Function adds multiple new tags.
    
    Behavior protected: Function handles multiple tag additions
    Bug detected: Function doesn't add all tags
    No internal dependency: Verifies API side effects
    Could fail: If batch processing is broken
    """
    monitor = {"name": "test", "tags": ["tag1", "tag2", "tag3"]}
    existing_tags = {
        "tag1": {"id": 1},
        "tag2": {"id": 2},
        "tag3": {"id": 3}
    }
    
    update_monitor_tags(
        api=mock_api,
        monitor_id=100,
        monitor=monitor,
        kuma_monitor={"id": 100, "name": "test", "tags": []},  # No existing tags
        existing_tags=existing_tags,
        delete=False
    )
    
    # Should add all 3 tags
    assert mock_api.add_monitor_tag.call_count == 3
    
    # Verify all tag IDs were used
    calls = mock_api.add_monitor_tag.call_args_list
    tag_ids = [call[1]["tag_id"] for call in calls]
    assert set(tag_ids) == {1, 2, 3}


def test_update_monitor_tags_empty_monitor_tags(mock_api, sample_kuma_monitor, sample_existing_tags):
    """
    BEHAVIOR TEST: Function handles empty tags list.
    
    Behavior protected: Function handles monitors without tags
    Bug detected: Function crashes or adds/deletes tags with empty list
    No internal dependency: Verifies API side effects
    Could fail: If empty list handling is broken
    """
    monitor = {"name": "test", "tags": []}
    
    update_monitor_tags(
        api=mock_api,
        monitor_id=100,
        monitor=monitor,
        kuma_monitor=sample_kuma_monitor,
        existing_tags=sample_existing_tags,
        delete=False
    )
    
    # Should not add or delete anything
    assert mock_api.add_monitor_tag.call_count == 0
    assert mock_api.delete_monitor_tag.call_count == 0


# =============================================================================
# ERROR HANDLING TESTS
# =============================================================================


def test_update_monitor_tags_monitor_without_tags_key_raises_keyerror(mock_api):
    """
    ERROR TEST: Function raises KeyError when monitor has no 'tags' key.
    
    Behavior protected: N/A - this is a bug that should be fixed
    Bug detected: 
    - **BUG**: Function accesses monitor['tags'] without checking if key exists
    - Should use monitor.get('tags', [])
    No internal dependency: Verifies exception (observable behavior)
    Could fail: If bug is fixed
    
    Test scenarios that would fail:
    1. Bug is fixed - function uses .get() instead of direct access
    2. Function handles missing key differently
    """
    monitor = {"name": "test"}  # No 'tags' key
    kuma_monitor = {"id": 100, "name": "test-monitor", "tags": []}
    existing_tags = {"tag1": {"id": 1, "name": "tag1"}}
    
    # This will raise KeyError because the code accesses monitor['tags'] without checking
    with pytest.raises(KeyError):
        update_monitor_tags(
            api=mock_api,
            monitor_id=100,
            monitor=monitor,
            kuma_monitor=kuma_monitor,
            existing_tags=existing_tags,
            delete=False
        )


def test_update_monitor_tags_kuma_monitor_tags_without_tag_id_key_raises_keyerror(
    mock_api, kuma_monitor_without_tag_id
):
    """
    ERROR TEST: Function raises KeyError when kuma_monitor tags don't have 'tag_id' key.
    
    Behavior protected: N/A - this is a bug that should be fixed
    Bug detected: 
    - **BUG**: Line 1003 in kuma_load.py accesses k['tag_id'] without checking key
    - Should use k.get('tag_id')
    No internal dependency: Verifies exception
    Could fail: If bug is fixed
    """
    monitor = {"name": "test", "tags": ["tag1"]}
    existing_tags = {"tag1": {"id": 1, "name": "tag1"}}
    
    # Should raise KeyError when trying to access k['tag_id'] at line 1003
    with pytest.raises(KeyError):
        update_monitor_tags(
            api=mock_api,
            monitor_id=100,
            monitor=monitor,
            kuma_monitor=kuma_monitor_without_tag_id,
            existing_tags=existing_tags,
            delete=False
        )


def test_update_monitor_tags_check_tag_not_in_tags_list_raises_keyerror(
    mock_api, kuma_monitor_without_tag_id
):
    """
    ERROR TEST: Function raises KeyError when checking tag membership.
    
    Behavior protected: N/A - this is a bug that should be fixed
    Bug detected: 
    - **BUG**: Line 1024 in kuma_load.py tries to access k['tag_id'] without checking
    - The code: `if tag in [k['tag_id'] for k in tags]`
    - Should use: `if tag in [k.get('tag_id') for k in tags if k.get('tag_id') is not None]`
    No internal dependency: Verifies exception
    Could fail: If bug is fixed
    """
    monitor = {"name": "test", "tags": ["tag3"]}  # tag3 exists in sample_existing_tags
    existing_tags = {"tag3": {"id": 3, "name": "tag3"}}
    
    # Should raise KeyError when trying to check if tag is in [k['tag_id'] for k in tags]
    with pytest.raises(KeyError):
        update_monitor_tags(
            api=mock_api,
            monitor_id=100,
            monitor=monitor,
            kuma_monitor=kuma_monitor_without_tag_id,
            existing_tags=existing_tags,
            delete=False
        )


# =============================================================================
# LOGGING TESTS
# =============================================================================


def test_update_monitor_tags_duplicate_tags_in_config_logs_warning(
    mock_api, empty_kuma_monitor, caplog
):
    """
    LOGGING TEST: Function logs duplicate tags warning.
    
    Behavior protected: Function detects and logs duplicate tags
    Bug detected: Function doesn't detect duplicates
    No internal dependency: Verifies logging (observable side effect)
    Could fail: If duplicate detection is broken
    """
    monitor = {"name": "test", "tags": ["tag1", "tag1", "tag2"]}
    existing_tags = {
        "tag1": {"id": 1, "name": "tag1"},
        "tag2": {"id": 2, "name": "tag2"}
    }
    
    caplog.set_level("INFO")
    update_monitor_tags(
        api=mock_api,
        monitor_id=100,
        monitor=monitor,
        kuma_monitor=empty_kuma_monitor,
        existing_tags=existing_tags,
        delete=False
    )
    
    # Should log duplicate tags
    assert any("Duplicate tags found" in record.message for record in caplog.records)
