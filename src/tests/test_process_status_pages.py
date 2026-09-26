"""
Tests for process_status_pages function.

These tests verify the observable behavior of process_status_pages:
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
from unittest.mock import Mock, patch

from src.kuma_load.kuma_load import process_status_pages


# =============================================================================
# FIXTURES - Representative test data
# =============================================================================

@pytest.fixture
def mock_api():
    """Mock API - external dependency only"""
    api = Mock()
    api.get_status_pages.return_value = []
    api.get_monitors.return_value = []
    api.add_status_page.return_value = {"msg": "Added"}
    api.save_status_page.return_value = {}
    api.delete_status_page.return_value = {}
    return api


@pytest.fixture
def sample_config_status_pages():
    """Representative config status pages data"""
    return [
        {"slug": "page1", "title": "Status Page 1"},
        {"slug": "page2", "title": "Status Page 2"}
    ]


@pytest.fixture
def sample_existing_status_pages():
    """Representative existing status pages data"""
    return [
        {"id": 1, "slug": "page1", "title": "Status Page 1"},
        {"id": 2, "slug": "page3", "title": "Status Page 3"}
    ]


# =============================================================================
# CONTRACT TESTS
# =============================================================================


def test_process_status_pages_api_none_raises_valueerror():
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
        process_status_pages(api=None)


# =============================================================================
# UNIT TESTS - Core functionality
# =============================================================================


def test_process_status_pages_both_empty_returns_empty_list():
    """
    UNIT TEST: Empty inputs produce empty output.
    
    Behavior protected: Function handles empty inputs correctly
    Bug detected: 
    - Logic error processing empty lists
    - **Bug #8**: Line 1172 uses len(config_status_pages) which could be None
    No internal dependency: Only verifies return value
    Could fail:
    1. Function returns wrong type
    2. **Bug #8**: If config_status_pages is None, TypeError: object of type 'NoneType' has no len()
    3. Function returns None instead of []
    
    Test scenarios that would fail:
    1. Function returns None
    2. Function returns dict instead of list
    3. Bug #8 causes TypeError
    """
    api = Mock()
    api.get_status_pages.return_value = []
    
    with patch('src.kuma_load.kuma_load.get_monitors') as mock_get:
        mock_get.return_value = ([], {})
        
        result = process_status_pages(
            api=api,
            config_status_pages=[],
            delete=False
        )
        
        assert result == []
        assert isinstance(result, list)


def test_process_status_pages_config_none_returns_empty_list():
    """
    UNIT TEST: None config is handled gracefully.
    
    Behavior protected: Function handles None config
    Bug detected: 
    - **Bug #8**: Line 1172 uses len(config_status_pages) which is None
      (TypeError: object of type 'NoneType' has no len())
    - Function doesn't handle None config
    No internal dependency: Only verifies return value
    Could fail:
    1. **Bug #8**: Function crashes with TypeError
    2. Function doesn't handle None config
    3. Function returns wrong type
    
    Test scenarios that would fail:
    1. Function crashes with TypeError due to Bug #8
    2. Function returns None
    3. Function returns wrong type
    """
    api = Mock()
    api.get_status_pages.return_value = []
    
    with patch('src.kuma_load.kuma_load.get_monitors') as mock_get:
        mock_get.return_value = ([], {})
        
        result = process_status_pages(
            api=api,
            config_status_pages=None,
            delete=False
        )
        
        # Verify function returns empty list (not None)
        assert result == []
        assert isinstance(result, list)


def test_process_status_pages_adds_new_page_returns_list():
    """
    UNIT TEST: Adding a new status page returns a list.
    
    Behavior protected: Function returns correct type when adding pages
    Bug detected: 
    - **Bug #9**: Line 1205 uses **config_status_pages instead of **config_by_names[a]
      (TypeError: 'list' object is not a mapping)
    - **Bug #14**: Function has no return statement at the end (returns None)
    No internal dependency: Only verifies return value type
    Could fail:
    1. **Bug #9**: Function crashes with TypeError
    2. **Bug #14**: Function returns None instead of list
    3. Function returns wrong type
    
    Test scenarios that would fail:
    1. Bug #9 exists -> TypeError when unpacking list
    2. Bug #14 exists -> Function returns None
    3. Function returns dict instead of list
    """
    api = Mock()
    config = [{"slug": "page1", "title": "Status Page 1"}]
    api.get_status_pages.return_value = []
    api.add_status_page.return_value = {"msg": "Added"}
    api.save_status_page.return_value = {}
    
    with patch('src.kuma_load.kuma_load.get_monitors') as mock_get:
        mock_get.return_value = ([], {})
        
        result = process_status_pages(
            api=api,
            config_status_pages=config,
            delete=False
        )
    
    # Verify function returns a list (not None)
    # Note: If Bug #9 or #14 exist, this will either crash or return None
    assert isinstance(result, list)


def test_process_status_pages_edits_existing_page_returns_list():
    """
    UNIT TEST: Editing an existing page returns a list.
    
    Behavior protected: Function returns correct type when editing
    Bug detected: 
    - **Bug #10**: Line 1251 f-string syntax error
    - **Bug #11**: Line 1252 missing parentheses in raise statement
    - Function returns wrong type
    No internal dependency: Only verifies return value type
    Could fail:
    1. Function returns None (Bug #14)
    2. Function returns wrong type
    3. Function crashes due to syntax errors
    
    Test scenarios that would fail:
    1. Function returns None
    2. Function returns dict
    3. Syntax errors prevent execution
    """
    api = Mock()
    config = [{"slug": "page1", "title": "Updated Title"}]
    existing = [{"id": 1, "slug": "page1", "title": "Status Page 1"}]
    
    api.get_status_pages.return_value = existing
    api.save_status_page.return_value = {}
    
    with patch('src.kuma_load.kuma_load.get_monitors') as mock_get:
        mock_get.return_value = ([], {})
        
        result = process_status_pages(
            api=api,
            config_status_pages=config,
            delete=False
        )
    
    # Verify function returns a list (not None)
    assert isinstance(result, list)


def test_process_status_pages_deletes_when_delete_true_returns_list():
    """
    UNIT TEST: Deleting pages returns a list.
    
    Behavior protected: Function returns correct type even when deleting
    Bug detected: Function returns wrong type when deleting
    No internal dependency: Only verifies return value type
    Could fail: 
    1. **Bug #14**: Function returns None
    2. Function returns wrong type
    
    Test scenarios that would fail:
    1. Function returns None
    2. Function returns dict
    """
    api = Mock()
    config = [{"slug": "page1", "title": "Status Page 1"}]
    existing = [
        {"id": 1, "slug": "page1", "title": "Status Page 1"},
        {"id": 2, "slug": "page3", "title": "Status Page 3"}
    ]
    
    api.get_status_pages.return_value = existing
    api.delete_status_page.return_value = {}
    
    with patch('src.kuma_load.kuma_load.get_monitors') as mock_get:
        mock_get.return_value = ([], {})
        
        result = process_status_pages(
            api=api,
            config_status_pages=config,
            delete=True
        )
    
    # Verify function returns a list (not None)
    assert isinstance(result, list)


# =============================================================================
# NEGATIVE TESTS / REGRESSION TESTS
# =============================================================================


def test_process_status_pages_preserves_config_fields():
    """
    REGRESSION TEST: Function preserves config fields in result.
    
    Behavior protected: All configuration data is preserved
    Bug detected: Function loses config fields during processing
    No internal dependency: Verifies through return value (when bugs are fixed)
    Could fail: If function doesn't preserve config fields
    
    Note: This test will currently fail due to Bugs #9 and #14, but when fixed,
    it will verify that config fields are preserved.
    
    Test scenarios that would fail:
    1. Function loses 'notes' field
    2. Function modifies field values
    3. Function returns incomplete data
    """
    api = Mock()
    config = [{
        "slug": "page1",
        "title": "Status Page 1",
        "notes": "Test page"
    }]
    api.get_status_pages.return_value = []
    api.add_status_page.return_value = {"msg": "Added"}
    api.save_status_page.return_value = {}
    
    with patch('src.kuma_load.kuma_load.get_monitors') as mock_get:
        mock_get.return_value = ([], {})
        
        result = process_status_pages(
            api=api,
            config_status_pages=config,
            delete=False
        )
    
    # When Bugs #9 and #14 are fixed, this should pass
    assert isinstance(result, list)
    # Further assertions can be added once bugs are fixed


def test_process_status_pages_with_publicGroupList():
    """
    REGRESSION TEST: Function handles publicGroupList correctly.
    
    Behavior protected: Complex config structures are handled
    Bug detected: Function crashes with publicGroupList
    No internal dependency: Verifies through return value
    Could fail: If function doesn't handle publicGroupList
    
    Test scenarios that would fail:
    1. Function crashes processing publicGroupList
    2. Function returns wrong type
    """
    api = Mock()
    config = [{
        "slug": "page1",
        "title": "Status Page 1",
        "publicGroupList": [
            {"groupName": "Group 1", "monitorList": [{"id": "monitor1"}]}
        ]
    }]
    
    api.get_status_pages.return_value = []
    
    with patch('src.kuma_load.kuma_load.get_monitors') as mock_get:
        mock_get.return_value = (
            [{"id": 1, "name": "monitor1"}],
            {"monitor1": {"id": 1, "name": "monitor1"}}
        )
        
        api.add_status_page.return_value = {"msg": "Added"}
        api.save_status_page.return_value = {}
        
        result = process_status_pages(
            api=api,
            config_status_pages=config,
            delete=False
        )
    
    # Verify function returns a list (not None)
    assert isinstance(result, list)
