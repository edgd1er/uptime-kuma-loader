"""
Tests for replace_tag_names_with_id function.

Note: This function has a bug - it iterates over existing_tags (which is a dict)
but tries to access d['name'], where d would be a string (the key), not the value.

The function is also not currently used in the codebase (the line that calls it is commented out).

The correct implementation should iterate over existing_tags.values() or use .items().
"""
import pytest
from typing import Dict, Any, List

from src.kuma_load.kuma_load import replace_tag_names_with_id


def test_replace_tag_names_with_id_bug_with_dict_input():
    """
    Test that shows the bug: when existing_tags is a dict, iterating over it
    gives keys (strings), not values (dicts).
    This causes TypeError when trying to access d['name'].
    """
    config_tags = ["tag1"]
    existing_tags = {"tag1": {"id": 1, "name": "tag1"}}
    
    # This will raise TypeError because the function iterates over dict keys
    # which are strings, not the dict values
    with pytest.raises(TypeError) as exc:
        replace_tag_names_with_id(config_tags, existing_tags)
    
    assert "string indices must be integers" in str(exc.value) or \
           "must be integers, not 'str'" in str(exc.value)


def test_replace_tag_names_with_id_works_with_list():
    """
    Test that the function works if we pass a list instead of dict.
    This shows what the intended behavior might have been.
    """
    config_tags = ["tag1", "tag2"]
    # Pass a list of tag dicts instead of a dict
    existing_tags_list = [
        {"id": 1, "name": "tag1"},
        {"id": 2, "name": "tag2"}
    ]
    
    # This should work if the function received a list
    result = replace_tag_names_with_id(config_tags, existing_tags_list)
    
    # Should return list of ids
    assert result == [1, 2]
