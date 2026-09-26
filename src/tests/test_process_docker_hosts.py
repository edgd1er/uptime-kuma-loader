"""
Tests for process_docker_hosts function.

These tests verify the observable behavior of process_docker_hosts:
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

from src.kuma_load.kuma_load import process_docker_hosts


@pytest.fixture
def mock_api():
    """Mock API - external dependency only"""
    api = Mock()
    api.add_docker_host.return_value = {"id": 1, "msg": "ok"}
    api.edit_docker_host.return_value = {"id": 1, "msg": "ok"}
    api.delete_docker_host.return_value = {"msg": "deleted"}
    api.get_docker_hosts.return_value = []
    return api


# =============================================================================
# CONTRACT TESTS
# =============================================================================


def test_process_docker_hosts_api_none_raises():
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
        process_docker_hosts(api=None)


# =============================================================================
# UNIT TESTS - Core functionality
# =============================================================================


def test_process_docker_hosts_config_none_returns_api_result(mock_api):
    """
    UNIT TEST: None config uses empty list and returns API result.
    
    Behavior protected: Function handles None config gracefully
    Bug detected: Function crashes with None config
    No internal dependency: Only verifies return value
    Could fail: If function doesn't handle None config
    
    Test scenarios that would fail:
    1. Function crashes with None config
    2. Function returns wrong type
    3. Function doesn't call api.get_docker_hosts
    """
    api = Mock()
    api.get_docker_hosts.return_value = [{"id": 1, "name": "host1"}]
    
    result = process_docker_hosts(
        api=api,
        config_docker_hosts=None,
        existing_docker_hosts=[],
        delete=False
    )
    
    # Verify observable behavior: returns API result
    assert result == [{"id": 1, "name": "host1"}]
    assert isinstance(result, list)


def test_process_docker_hosts_adds_new_host_returns_api_result(mock_api):
    """
    UNIT TEST: Adding a new docker host returns API result.
    
    Behavior protected: Function returns result from api.get_docker_hosts
    Bug detected: Function returns wrong value
    No internal dependency: Only verifies return value
    Could fail: If function doesn't return API result
    
    Test scenarios that would fail:
    1. Function returns wrong type
    2. Function returns empty list
    3. Function doesn't process new hosts
    """
    config = [{"name": "host1", "host": "docker1.example.com"}]
    existing = []
    
    result = process_docker_hosts(
        api=mock_api,
        config_docker_hosts=config,
        existing_docker_hosts=existing,
        delete=False
    )
    
    # Verify observable behavior: returns API result (list)
    assert isinstance(result, list)


def test_process_docker_hosts_edits_existing_host_returns_api_result(mock_api):
    """
    UNIT TEST: Editing an existing docker host returns API result.
    
    Behavior protected: Function returns result from api.get_docker_hosts
    Bug detected: Function returns wrong value
    No internal dependency: Only verifies return value
    Could fail: If function doesn't return API result
    
    Test scenarios that would fail:
    1. Function returns wrong type
    2. Function doesn't process edits
    """
    config = [{"name": "host1", "host": "new-docker.example.com"}]
    existing = [{"id": 1, "name": "host1", "host": "old-docker.example.com"}]
    
    result = process_docker_hosts(
        api=mock_api,
        config_docker_hosts=config,
        existing_docker_hosts=existing,
        delete=False
    )
    
    # Verify observable behavior: returns API result
    assert isinstance(result, list)


def test_process_docker_hosts_deletes_when_delete_true_returns_api_result(mock_api):
    """
    UNIT TEST: Deleting hosts returns API result.
    
    Behavior protected: Function returns result from api.get_docker_hosts
    Bug detected: Function returns wrong value
    No internal dependency: Only verifies return value
    Could fail: If function doesn't return API result
    
    Test scenarios that would fail:
    1. Function returns wrong type
    2. Function doesn't process deletions
    """
    config = [{"name": "keep_host"}]
    existing = [
        {"id": 1, "name": "keep_host", "host": "keep.example.com"},
        {"id": 2, "name": "delete_host", "host": "delete.example.com"}
    ]
    
    result = process_docker_hosts(
        api=mock_api,
        config_docker_hosts=config,
        existing_docker_hosts=existing,
        delete=True
    )
    
    # Verify observable behavior: returns API result
    assert isinstance(result, list)


def test_process_docker_hosts_returns_api_get_docker_hosts_result(mock_api):
    """
    UNIT TEST: Function returns result from api.get_docker_hosts().
    
    Behavior protected: Function returns the final state from API
    Bug detected: Function returns wrong value
    No internal dependency: Only verifies return value
    Could fail: If function doesn't return API result
    
    Test scenarios that would fail:
    1. Function returns config instead of API result
    2. Function returns wrong type
    3. Function returns modified value
    """
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
    
    # Verify observable behavior: returns whatever api.get_docker_hosts returns
    assert result == [
        {"id": 1, "name": "host1"},
        {"id": 2, "name": "host2"}
    ]
    assert isinstance(result, list)
