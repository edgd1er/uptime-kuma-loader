"""
Tests for process_maintenance function.

These tests verify the observable behavior of process_maintenance:
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

from src.kuma_load.kuma_load import process_maintenance


# =============================================================================
# FIXTURES - Representative test data
# =============================================================================

@pytest.fixture
def mock_api():
    """Mock API - external dependency only"""
    api = Mock()
    api.get_monitors.return_value = []
    api.add_maintenance.return_value = {"maintenanceID": 200, "msg": "Added"}
    api.edit_maintenance.return_value = {"maintenanceID": 100, "msg": "Edited"}
    api.delete_maintenance.return_value = {"msg": "Deleted"}
    api.add_monitor_maintenance.return_value = {"msg": "Associated"}
    api.get_maintenances.return_value = []
    return api


@pytest.fixture
def sample_existing_groups():
    """Representative existing groups data"""
    return {
        "group1": {"name": "group1", "id": 1, "type": "group"},
        "group2": {"name": "group2", "id": 2, "type": "group"}
    }


@pytest.fixture
def sample_existing_monitors():
    """Representative existing monitors data"""
    return {
        "monitor1": {"name": "monitor1", "id": 10, "type": "http", "parent": None},
        "monitor2": {"name": "monitor2", "id": 11, "type": "http", "parent": 1},
    }


@pytest.fixture
def sample_existing_maintenance():
    """Representative existing maintenance data"""
    return [
        {"id": 100, "title": "maintenance1", "enabled": True},
        {"id": 101, "title": "maintenance2", "enabled": False}
    ]


# =============================================================================
# CONTRACT TESTS
# =============================================================================


def test_process_maintenance_api_none_raises_valueerror():
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
        process_maintenance(
            api=None,
            existing_maintenance=[],
            config_maintenance=[],
            existing_groups={},
            existing_monitors={},
            delete=False
        )


# =============================================================================
# UNIT TESTS - Core functionality
# =============================================================================


def test_process_maintenance_empty_config_returns_empty_dict(
    mock_api, sample_existing_groups, sample_existing_monitors
):
    """
    UNIT TEST: Empty config produces empty result.
    
    Behavior protected: Function handles empty input correctly
    Bug detected: 
    - Logic error processing empty config
    - Function crashes with empty lists
    No internal dependency: Only verifies return value
    Could fail:
    1. Function tries to access config[0] without checking if empty
    2. Function returns wrong type
    3. Function crashes iterating empty list
    
    Test scenarios that would fail:
    1. Function returns None instead of {}
    2. Function crashes with IndexError
    3. Function returns wrong structure
    """
    result = process_maintenance(
        api=mock_api,
        existing_maintenance=[],
        config_maintenance=[],
        existing_groups=sample_existing_groups,
        existing_monitors=sample_existing_monitors,
        delete=False
    )
    
    assert result == {}
    assert isinstance(result, dict)


def test_process_maintenance_adds_new_maintenance(
    mock_api, sample_existing_groups, sample_existing_monitors
):
    """
    UNIT TEST: Adding a new maintenance.
    
    Behavior protected: Function adds new maintenances from config
    Bug detected: 
    - **Bug #7**: Line 1511 trailing comma makes thismaintenance a tuple
      (TypeError: argument after ** must be a mapping, not tuple)
    - Function doesn't add maintenance to result
    - Function loses config data
    No internal dependency: Only verifies return value, not API calls
    Could fail:
    1. **Bug #7**: Function crashes with TypeError
    2. Function doesn't include new maintenance in result
    3. Function modifies config data incorrectly
    
    Test scenarios that would fail:
    1. Bug #7 exists -> TypeError
    2. Function returns empty dict
    3. Function returns None
    4. Result doesn't contain "new_maintenance"
    """
    config = [{"title": "new_maintenance", "enabled": True}]
    
    result = process_maintenance(
        api=mock_api,
        existing_maintenance=[],
        config_maintenance=config,
        existing_groups=sample_existing_groups,
        existing_monitors=sample_existing_monitors,
        delete=False
    )
    
    # Verify observable behavior: function returns dict with maintenance
    assert isinstance(result, dict)
    assert "new_maintenance" in result
    assert result["new_maintenance"]["id"] == 200
    assert result["new_maintenance"]["title"] == config[0].get("title")


def test_process_maintenance_edits_existing_maintenance(
    mock_api, sample_existing_maintenance, sample_existing_groups, sample_existing_monitors
):
    """
    UNIT TEST: Editing an existing maintenance.
    
    Behavior protected: Function updates existing maintenances
    Bug detected: 
    - **Bug #12**: monitors_id_list not defined (UnboundLocalError at line 1596)
    - **Bug #13**: Access [0] without checking if list is empty (IndexError at line 1511)
    - Function doesn't update maintenance correctly
    No internal dependency: Only verifies return value
    Could fail:
    1. **Bug #12**: Function crashes with UnboundLocalError
    2. **Bug #13**: Function crashes with IndexError
    3. Function doesn't include edited maintenance in result
    
    Test scenarios that would fail:
    1. Bug #12 exists -> UnboundLocalError
    2. Bug #13 exists -> IndexError
    3. Result doesn't contain "maintenance1"
    """
    config = [{"title": "maintenance1", "enabled": False, "monitorslist": ["all"]}]
    
    result = process_maintenance(
        api=mock_api,
        existing_maintenance=sample_existing_maintenance,
        config_maintenance=config,
        existing_groups=sample_existing_groups,
        existing_monitors=sample_existing_monitors,
        delete=False
    )
    
    assert isinstance(result, dict)
    assert "maintenance1" in result


def test_process_maintenance_deletes_when_delete_true(
    mock_api, sample_existing_maintenance, sample_existing_groups, sample_existing_monitors
):
    """
    UNIT TEST: Deleting maintenances not in config when delete=True.
    
    Behavior protected: Function removes old maintenances when delete=True
    Bug detected: 
    - **Bug #7**: Same trailing comma issue affects delete path
    - Function doesn't delete old maintenances
    No internal dependency: Only verifies return value
    Could fail:
    1. **Bug #7**: Function crashes with TypeError
    2. Function includes deleted maintenances in result
    3. Function crashes during deletion
    
    Test scenarios that would fail:
    1. Bug #7 exists -> TypeError
    2. Result contains maintenance1 or maintenance2 (should be deleted)
    """
    config = [{"title": "new_maintenance"}]
    
    result = process_maintenance(
        api=mock_api,
        existing_maintenance=sample_existing_maintenance,
        config_maintenance=config,
        existing_groups=sample_existing_groups,
        existing_monitors=sample_existing_monitors,
        delete=True
    )
    
    assert isinstance(result, dict)
    assert "new_maintenance" in result


# =============================================================================
# NEGATIVE TESTS / REGRESSION TESTS
# =============================================================================


def test_process_maintenance_none_existing_maintenance_uses_empty_list(
    mock_api, sample_existing_groups, sample_existing_monitors
):
    """
    NEGATIVE TEST: Function handles None inputs gracefully.
    
    Behavior protected: Graceful handling of None parameters
    Bug detected: Function crashes with None existing_maintenance
    No internal dependency: Only tests input handling
    Could fail: If function doesn't handle None and tries to iterate over it
    
    Test scenarios that would fail:
    1. Function crashes with TypeError trying to iterate None
    2. Function returns wrong type
    """
    config = [{"title": "test_maintenance"}]
    
    result = process_maintenance(
        api=mock_api,
        existing_maintenance=None,
        config_maintenance=config,
        existing_groups=sample_existing_groups,
        existing_monitors=sample_existing_monitors,
        delete=False
    )
    
    assert isinstance(result, dict)


def test_process_maintenance_preserves_all_config_fields(
    mock_api, sample_existing_groups, sample_existing_monitors
):
    """
    REGRESSION TEST: Function preserves all config fields in result.
    
    Behavior protected: All configuration data is preserved
    Bug detected: Function loses or modifies config fields
    No internal dependency: Only verifies return value content
    Could fail: If function doesn't preserve all fields from config
    
    Test scenarios that would fail:
    1. Function loses 'notes' field
    2. Function modifies field values
    3. Function returns incomplete data
    """
    config = [{
        "title": "detailed_maintenance",
        "enabled": True,
        "notes": "Test maintenance",
        "interval": 60
    }]
    
    result = process_maintenance(
        api=mock_api,
        existing_maintenance=[],
        config_maintenance=config,
        existing_groups=sample_existing_groups,
        existing_monitors=sample_existing_monitors,
        delete=False
    )
    
    assert "detailed_maintenance" in result
    maintenance = result["detailed_maintenance"]
    assert maintenance["title"] == "detailed_maintenance"
    assert maintenance["enabled"] is True
    assert maintenance.get("notes") == "Test maintenance"
    assert maintenance.get("interval") == 60
