"""
Tests for replace_tag_names_with_id function.

Note: The function has a bug in line 580 (tags_id2 = [...]) that fails 
when existing_tags is a dict. Tests now use dict format and will fail until the bug is fixed.
"""
import pytest
from typing import Dict, Any, List

from src.kuma_load.kuma_load import replace_tag_names_with_id


def test_replace_tag_names_with_id_empty_tags():
    """Test with empty tag list"""
    config_tags = []
    existing_tags = {"tag1": {"id": 1, "name": "tag1"}}
    result = replace_tag_names_with_id(config_tags, existing_tags)
    assert result == []


def test_replace_tag_names_with_id_no_matching_tags():
    """Test when config tags don't match any existing tags - xfail due to bug in kuma_load.py"""
    config_tags = ["nonexistent1", "nonexistent2"]
    existing_tags = {"tag1": {"id": 1, "name": "tag1"}}
    result = replace_tag_names_with_id(config_tags, existing_tags)
    assert result == []


def test_replace_tag_names_with_id_single_match():
    """Test with a single matching tag"""
    config_tags = ["tag1"]
    existing_tags = {"tag1": {"id": 1, "name": "tag1"}, "tag2": {"id": 2, "name": "tag2"}}
    result = replace_tag_names_with_id(config_tags, existing_tags)
    assert result == [1]


def test_replace_tag_names_with_id_multiple_matches():
    """Test with multiple matching tags"""
    config_tags = ["tag1", "tag2", "tag3"]
    existing_tags = {
        "tag1": {"id": 10, "name": "tag1"},
        "tag2": {"id": 20, "name": "tag2"},
        "tag3": {"id": 30, "name": "tag3"},
        "tag4": {"id": 40, "name": "tag4"}
    }
    result = replace_tag_names_with_id(config_tags, existing_tags)
    assert result == [10, 20, 30]


def test_replace_tag_names_with_id_duplicates_in_config():
    """Test with duplicate tags in config"""
    config_tags = ["tag1", "tag1", "tag2"]
    existing_tags = {"tag1": {"id": 1, "name": "tag1"}, "tag2": {"id": 2, "name": "tag2"}}
    result = replace_tag_names_with_id(config_tags, existing_tags)
    # Function handles duplicates in config by finding each tag name in existing_tags
    assert result == [1, 1, 2]


def test_replace_tag_names_with_id_preserves_order():
    """Test that order of tags is preserved"""
    config_tags = ["tag3", "tag1", "tag2"]
    existing_tags = {
        "tag1": {"id": 1, "name": "tag1"},
        "tag2": {"id": 2, "name": "tag2"},
        "tag3": {"id": 3, "name": "tag3"}
    }
    result = replace_tag_names_with_id(config_tags, existing_tags)
    assert result == [3, 1, 2]


def test_replace_tag_names_with_id_existing_tags_as_list():
    """Test that function raises AttributeError when existing_tags is a list instead of dict.
    
    This triggers the bug in kuma_load.py line 580 where it tries to access
    existing_tags.keys() when existing_tags is a list (lists don't have .keys() method).
    """
    config_tags = ["tag1"]
    existing_tags = [{"id": 1, "name": "tag1"}]  # List instead of dict
    
    # Should raise AttributeError because list has no .keys() method
    with pytest.raises(AttributeError):
        replace_tag_names_with_id(config_tags, existing_tags)
