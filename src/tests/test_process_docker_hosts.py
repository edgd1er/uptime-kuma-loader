"""
Tests for process_docker_hosts function.
"""
import pytest
from unittest.mock import Mock
from typing import Dict, Any, List

from src.kuma_load.kuma_load import process_docker_hosts


@pytest.fixture
def mock_api():
    """Create a mock API for testing"""
    api = Mock()
    api.add_docker_host = Mock()
    api.edit_docker_host = Mock()
    api.delete_docker_host = Mock()
    api.get_docker_hosts = Mock()
    return api


def test_process_docker_hosts_api_none_raises():
    """Test that None API raises ValueError"""
    with pytest.raises(ValueError, match="api must not be None"):
        process_docker_hosts(api=None)


def test_process_docker_hosts_config_none():
    """Test with None config uses empty list"""
    api = Mock()
    api.get_docker_hosts.return_value = []
    
    result = process_docker_hosts(
        api=api,
        config_docker_hosts=None,
        existing_docker_hosts=[],
        delete=False
    )
    
    # Should return result from api.get_docker_hosts
    api.get_docker_hosts.assert_called_once()


def test_process_docker_hosts_adds_new_host(mock_api):
    """Test adding a new docker host"""
    config = [{"name": "host1", "host": "docker1.example.com"}]
    existing = []
    
    mock_api.add_docker_host.return_value = {"id": 1, "msg": "ok"}
    mock_api.get_docker_hosts.return_value = []
    
    result = process_docker_hosts(
        api=mock_api,
        config_docker_hosts=config,
        existing_docker_hosts=existing,
        delete=False
    )
    
    # Should have called add_docker_host
    mock_api.add_docker_host.assert_called_once()
    call_kwargs = mock_api.add_docker_host.call_args[1]
    assert call_kwargs["name"] == "host1"
    assert call_kwargs["host"] == "docker1.example.com"


def test_process_docker_hosts_edits_existing_host(mock_api):
    """Test editing an existing docker host"""
    config = [{"name": "host1", "host": "new-docker.example.com"}]
    existing = [{"id": 1, "name": "host1", "host": "old-docker.example.com"}]
    
    mock_api.edit_docker_host.return_value = {"id": 1, "msg": "ok"}
    mock_api.get_docker_hosts.return_value = []
    
    result = process_docker_hosts(
        api=mock_api,
        config_docker_hosts=config,
        existing_docker_hosts=existing,
        delete=False
    )
    
    # Should have called edit_docker_host
    mock_api.edit_docker_host.assert_called_once()
    call_kwargs = mock_api.edit_docker_host.call_args[1]
    assert call_kwargs["id_"] == 1
    assert call_kwargs["name"] == "host1"
    assert call_kwargs["host"] == "new-docker.example.com"


def test_process_docker_hosts_deletes_when_delete_true(mock_api):
    """Test deleting docker hosts not in config when delete=True"""
    config = [{"name": "keep_host"}]
    existing = [
        {"id": 1, "name": "keep_host", "host": "keep.example.com"},
        {"id": 2, "name": "delete_host", "host": "delete.example.com"}
    ]
    
    mock_api.delete_docker_host.return_value = {"msg": "deleted"}
    mock_api.get_docker_hosts.return_value = []
    
    result = process_docker_hosts(
        api=mock_api,
        config_docker_hosts=config,
        existing_docker_hosts=existing,
        delete=True
    )
    
    # Should have deleted the host not in config
    mock_api.delete_docker_host.assert_called_once()
    call_kwargs = mock_api.delete_docker_host.call_args[1]
    assert call_kwargs["id_"] == 2


def test_process_docker_hosts_returns_api_get_docker_hosts_result(mock_api):
    """Test that function returns result from api.get_docker_hosts()"""
    config = []
    existing = []
    
    mock_api.get_docker_hosts.return_value = [
        {"id": 1, "name": "host1"},
        {"id": 2, "name": "host2"}
    ]
    
    result = process_docker_hosts(
        api=mock_api,
        config_docker_hosts=config,
        existing_docker_hosts=existing,
        delete=False
    )
    
    # Should return whatever api.get_docker_hosts returns
    assert result == [
        {"id": 1, "name": "host1"},
        {"id": 2, "name": "host2"}
    ]
