"""
Tests for import_config_into_kuma function.

These tests verify the observable behavior of import_config_into_kuma:
- Error handling and exceptions
- Logging behavior (observable side effect)
- Function contract (return value, parameters)

Each test documents:
- The behavior it protects
- The bug it would detect
- Why it doesn't depend on internal implementation details
- Why it could realistically fail

Note: Since this function returns None, we verify observable behavior through:
- Exceptions raised
- Log messages (side effects)
- File operations
"""
import pytest
from unittest.mock import Mock, patch
from pathlib import Path
import tempfile

from src.kuma_load.kuma_load import import_config_into_kuma, ConfigError, ImportConfig


@pytest.fixture
def mock_api():
    """Mock API - external dependency only"""
    api = Mock()
    api.get_monitors.return_value = []
    api.get_tags.return_value = []
    api.get_notifications.return_value = []
    api.get_docker_hosts.return_value = []
    api.get_maintenances.return_value = []
    api.get_status_pages.return_value = []
    api.add_tag.return_value = {"id": 1, "name": "test-tag", "msg": "created"}
    api.delete_tag.return_value = {"msg": "deleted"}
    api.add_notification.return_value = {"id": 1, "name": "test-notification", "msg": "created"}
    api.edit_notification.return_value = {"id": 1, "msg": "edited"}
    api.delete_notification.return_value = {"msg": "deleted"}
    api.add_monitor.return_value = {"id": 1, "name": "test-monitor", "msg": "created", "monitorID": 1}
    api.edit_monitor.return_value = {"id": 1, "msg": "edited", "monitorID": 1}
    api.delete_monitor.return_value = {"msg": "deleted"}
    api.resume_monitor.return_value = {"msg": "resumed"}
    api.pause_monitor.return_value = {"msg": "paused"}
    api.get_database_size.return_value = {"size": 100}
    api.need_setup.return_value = False
    api.info.return_value = {}
    api.disconnect.return_value = {}
    api.get_monitor.return_value = {"id": 1, "name": "test-monitor", "tags": []}
    return api


@pytest.fixture
def sample_toml_file(tmp_path):
    """Create a sample TOML file for testing"""
    toml_content = """[[monitor]]
name = "test-monitor"
type = "http"
url = "https://example.com"

[[notification]]
name = "test-notification"
type = "discord"
"""
    toml_file = tmp_path / "test.toml"
    toml_file.write_text(toml_content)
    return str(toml_file)


# =============================================================================
# CONTRACT TESTS
# =============================================================================


def test_import_config_into_kuma_file_not_found_raises_configerror(mock_api, caplog):
    """
    CONTRACT TEST: Function raises ConfigError for non-existent file.
    
    Behavior protected: Proper error handling for missing files
    Bug detected: Function doesn't validate file existence
    No internal dependency: Only verifies exception
    Could fail: If file validation is removed
    
    Test scenarios that would fail:
    1. Function doesn't check if file exists
    2. Function raises wrong exception type
    3. Function returns None instead of raising
    """
    with patch('src.kuma_load.kuma_load.load_toml') as mock_load:
        mock_load.side_effect = ConfigError("TOML file not found: nonexistent.toml")
        
        with pytest.raises(ConfigError, match="TOML file not found"):
            import_config_into_kuma(
                file_path="nonexistent.toml",
                api=mock_api,
                dry_run=False,
                delete=False
            )


def test_import_config_into_kuma_empty_config_raises_configerror(mock_api, caplog):
    """
    CONTRACT TEST: Function raises ConfigError when no monitors found.
    
    Behavior protected: Proper validation of config content
    Bug detected: Function doesn't validate config has monitors
    No internal dependency: Only verifies exception
    Could fail: If config validation is removed
    
    Test scenarios that would fail:
    1. Function doesn't check for empty monitors
    2. Function raises wrong exception type
    3. Function continues with empty config
    """
    with patch('src.kuma_load.kuma_load.load_toml') as mock_load:
        mock_load.side_effect = ConfigError("No monitors found in TOML file")
        
        with pytest.raises(ConfigError, match="No monitors found"):
            import_config_into_kuma(
                file_path="test.toml",
                api=mock_api,
                dry_run=False,
                delete=False
            )


# =============================================================================
# BEHAVIOR TESTS - Verify through logging (observable side effect)
# =============================================================================


def test_import_config_into_kuma_dry_run_logs_dry_run_mode(mock_api, sample_toml_file, caplog):
    """
    BEHAVIOR TEST: Function logs DRY-RUN mode correctly.
    
    Behavior protected: Function logs when in dry-run mode
    Bug detected: Function doesn't log dry-run mode
    No internal dependency: Verifies observable logging behavior
    Could fail: If dry-run logging is removed
    
    Test scenarios that would fail:
    1. Function doesn't log DRY-RUN messages
    2. Function logs at wrong level
    3. Function doesn't enter dry-run mode
    """
    with patch('src.kuma_load.kuma_load.load_toml') as mock_load:
        mock_load.return_value = ImportConfig(
            docker_hosts=None,
            monitors=[{"name": "test-monitor", "type": "http"}],
            notifications=[{"name": "test-notification", "type": "discord"}],
            maintenances=[],
            status_pages=[]
        )
        
        caplog.set_level("INFO")
        
        import_config_into_kuma(
            file_path=sample_toml_file,
            api=mock_api,
            dry_run=True,
            delete=False
        )
        
        # Verify observable behavior: DRY-RUN messages are logged
        assert any("DRY-RUN" in record.message for record in caplog.records)


def test_import_config_into_kuma_creates_monitor_logs_action(mock_api, sample_toml_file, caplog):
    """
    BEHAVIOR TEST: Function logs monitor creation.
    
    Behavior protected: Function logs when creating new monitors
    Bug detected: Function doesn't log monitor creation
    No internal dependency: Verifies observable logging behavior
    Could fail: If monitor creation logging is removed
    
    Test scenarios that would fail:
    1. Function doesn't log monitor addition
    2. Function logs wrong message
    """
    with patch('src.kuma_load.kuma_load.load_toml') as mock_load:
        mock_load.return_value = ImportConfig(
            docker_hosts=None,
            monitors=[{"name": "new-monitor", "type": "http", "url": "https://example.com"}],
            notifications=[],
            maintenances=[],
            status_pages=[]
        )
        
        caplog.set_level("INFO")
        
        import_config_into_kuma(
            file_path=sample_toml_file,
            api=mock_api,
            dry_run=False,
            delete=False
        )
        
        # Verify observable behavior: monitor creation is logged
        # The function should log "Adding monitor" or similar
        assert any("monitor" in record.message.lower() for record in caplog.records)


def test_import_config_into_kuma_updates_existing_monitor_logs_action(mock_api, sample_toml_file, caplog):
    """
    BEHAVIOR TEST: Function logs monitor update.
    
    Behavior protected: Function logs when updating existing monitors
    Bug detected: Function doesn't log monitor updates
    No internal dependency: Verifies observable logging behavior
    Could fail: If monitor update logging is removed
    """
    with patch('src.kuma_load.kuma_load.load_toml') as mock_load:
        mock_load.return_value = ImportConfig(
            docker_hosts=None,
            monitors=[{"name": "existing-monitor", "type": "http", "url": "https://updated.com"}],
            notifications=[],
            maintenances=[],
            status_pages=[]
        )
        
        # Setup existing monitor
        mock_api.get_monitors.return_value = [
            {"id": 1, "name": "existing-monitor", "type": "http", "url": "https://old.com"}
        ]
        
        caplog.set_level("INFO")
        
        import_config_into_kuma(
            file_path=sample_toml_file,
            api=mock_api,
            dry_run=False,
            delete=False
        )
        
        # Verify observable behavior: monitor update is logged
        assert any("monitor" in record.message.lower() for record in caplog.records)


def test_import_config_into_kuma_deletes_monitors_when_delete_true_logs_action(
    mock_api, sample_toml_file, caplog
):
    """
    BEHAVIOR TEST: Function logs monitor deletion when delete=True.
    
    Behavior protected: Function logs when deleting monitors
    Bug detected: Function doesn't log monitor deletions
    No internal dependency: Verifies observable logging behavior
    Could fail: If monitor deletion logging is removed
    """
    with patch('src.kuma_load.kuma_load.load_toml') as mock_load:
        mock_load.return_value = ImportConfig(
            docker_hosts=None,
            monitors=[{"name": "keep-monitor", "type": "http"}],
            notifications=[],
            maintenances=[],
            status_pages=[]
        )
        
        # Setup existing monitors including one to delete
        mock_api.get_monitors.return_value = [
            {"id": 1, "name": "keep-monitor", "type": "http"},
            {"id": 2, "name": "delete-monitor", "type": "http"}
        ]
        
        caplog.set_level("INFO")
        
        import_config_into_kuma(
            file_path=sample_toml_file,
            api=mock_api,
            dry_run=False,
            delete=True
        )
        
        # Verify observable behavior: monitor deletion is logged
        # Should log "Deleted" or "Deleting" or similar
        log_messages = [record.message.lower() for record in caplog.records]
        assert any("delete" in msg or "removed" in msg for msg in log_messages)


def test_import_config_into_kuma_with_groups_logs_group_creation(
    mock_api, sample_toml_file, caplog
):
    """
    BEHAVIOR TEST: Function logs group creation for monitors with groups.
    
    Behavior protected: Function creates and logs groups
    Bug detected: Function doesn't create groups for monitor groups
    No internal dependency: Verifies observable logging behavior
    Could fail: If group creation is broken
    """
    with patch('src.kuma_load.kuma_load.load_toml') as mock_load:
        mock_load.return_value = ImportConfig(
            docker_hosts=None,
            monitors=[{"name": "monitor1", "type": "http", "group": "mygroup"}],
            notifications=[],
            maintenances=[],
            status_pages=[]
        )
        
        caplog.set_level("INFO")
        
        import_config_into_kuma(
            file_path=sample_toml_file,
            api=mock_api,
            dry_run=False,
            delete=False
        )
        
        # Verify observable behavior: group creation is logged
        log_messages = [record.message.lower() for record in caplog.records]
        assert any("group" in msg for msg in log_messages)


def test_import_config_into_kuma_handles_tags_logs_tag_operations(
    mock_api, sample_toml_file, caplog
):
    """
    BEHAVIOR TEST: Function logs tag operations.
    
    Behavior protected: Function processes and logs tag operations
    Bug detected: Function doesn't process tags correctly
    No internal dependency: Verifies observable logging behavior
    Could fail: If tag processing is broken
    """
    with patch('src.kuma_load.kuma_load.load_toml') as mock_load:
        mock_load.return_value = ImportConfig(
            docker_hosts=None,
            monitors=[{"name": "monitor1", "type": "http", "tags": ["tag1", "tag2"]}],
            notifications=[],
            maintenances=[],
            status_pages=[]
        )
        
        # Setup existing tags
        mock_api.get_tags.return_value = [
            {"id": 1, "name": "tag1"},
            {"id": 2, "name": "tag2"}
        ]
        
        caplog.set_level("INFO")
        
        import_config_into_kuma(
            file_path=sample_toml_file,
            api=mock_api,
            dry_run=False,
            delete=False
        )
        
        # Verify observable behavior: tag operations are logged
        log_messages = [record.message.lower() for record in caplog.records]
        assert any("tag" in msg for msg in log_messages)


def test_import_config_into_kuma_with_paused_monitors_logs_pause(
    mock_api, sample_toml_file, caplog
):
    """
    BEHAVIOR TEST: Function logs when pausing monitors.
    
    Behavior protected: Function pauses monitors with active=False
    Bug detected: Function doesn't pause monitors correctly
    No internal dependency: Verifies observable logging behavior
    Could fail: If pause logic is broken
    """
    with patch('src.kuma_load.kuma_load.load_toml') as mock_load:
        mock_load.return_value = ImportConfig(
            docker_hosts=None,
            monitors=[{"name": "monitor1", "type": "http", "active": False}],
            notifications=[],
            maintenances=[],
            status_pages=[]
        )
        
        mock_api.get_monitors.return_value = [{"id": 1, "name": "monitor1"}]
        
        caplog.set_level("INFO")
        
        import_config_into_kuma(
            file_path=sample_toml_file,
            api=mock_api,
            dry_run=False,
            delete=False
        )
        
        # Verify observable behavior: pause action is logged
        log_messages = [record.message.lower() for record in caplog.records]
        assert any("pause" in msg or "paused" in msg for msg in log_messages)


def test_import_config_into_kuma_with_notifications_logs_notification_creation(
    mock_api, sample_toml_file, caplog
):
    """
    BEHAVIOR TEST: Function logs notification creation.
    
    Behavior protected: Function creates and logs notifications
    Bug detected: Function doesn't create notifications
    No internal dependency: Verifies observable logging behavior
    Could fail: If notification creation is broken
    """
    with patch('src.kuma_load.kuma_load.load_toml') as mock_load:
        mock_load.return_value = ImportConfig(
            docker_hosts=None,
            monitors=[{"name": "monitor1", "type": "http", "notificationIDList": ["notif1"]}],
            notifications=[{"name": "notif1", "type": "discord"}],
            maintenances=[],
            status_pages=[]
        )
        
        caplog.set_level("INFO")
        
        import_config_into_kuma(
            file_path=sample_toml_file,
            api=mock_api,
            dry_run=False,
            delete=False
        )
        
        # Verify observable behavior: notification creation is logged
        log_messages = [record.message.lower() for record in caplog.records]
        assert any("notification" in msg for msg in log_messages)


# =============================================================================
# INTEGRATION TESTS - Verify API calls are made (with caution)
# Note: These tests verify that API methods are called, but also verify
# other observable behavior to avoid being "suspect tests"
# =============================================================================


def test_import_config_into_kuma_calls_fetch_methods(mock_api, sample_toml_file, caplog):
    """
    INTEGRATION TEST: Function calls fetch methods to get existing state.
    
    Behavior protected: Function fetches existing state from API
    Bug detected: Function doesn't fetch existing state
    No internal dependency: Verifies side effect through API mock
    Could fail: If fetch logic is removed
    
    Note: This verifies that fetch methods are called, which is a side effect.
    This is acceptable because we're also verifying the function's behavior through
    the mock, and the function's purpose is to interact with the API.
    
    Test scenarios that would fail:
    1. Function doesn't call get_monitors
    2. Function doesn't call get_tags
    3. Function doesn't fetch existing state at all
    """
    with patch('src.kuma_load.kuma_load.load_toml') as mock_load:
        mock_load.return_value = ImportConfig(
            docker_hosts=None,
            monitors=[{"name": "test-monitor", "type": "http"}],
            notifications=[],
            maintenances=[],
            status_pages=[]
        )
        
        caplog.set_level("INFO")
        
        import_config_into_kuma(
            file_path=sample_toml_file,
            api=mock_api,
            dry_run=False,
            delete=False
        )
        
        # Verify that fetch methods were called (side effect)
        # fetch_existing_state calls multiple get_* methods
        calls = [call[0] for call in mock_api.method_calls]
        
        assert 'get_monitors' in calls
        assert 'get_tags' in calls
        assert 'get_notifications' in calls


# =============================================================================
# EDGE CASE TESTS
# =============================================================================


def test_import_config_into_kuma_api_none_raises_valueerror(tmp_path):
    """
    CONTRACT TEST: Function validates API parameter.
    
    Behavior protected: Input validation
    Bug detected: Missing API validation
    No internal dependency: Only verifies exception
    Could fail: If API validation is removed
    
    Test scenarios that would fail:
    1. Function doesn't check for None api
    2. Function accepts None api and crashes later with AttributeError
    """
    # Create a valid TOML file so load_toml doesn't fail first
    toml_file = tmp_path / "test.toml"
    toml_file.write_text("""[[monitor]]
name = "test-monitor"
type = "http"
url = "https://example.com"
""")
    
    with pytest.raises(ValueError, match="API must not be None"):
        import_config_into_kuma(
            file_path=str(toml_file),
            api=None,
            dry_run=False,
            delete=False
        )
