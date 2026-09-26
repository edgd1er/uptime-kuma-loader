"""
Tests for convert_time_range function.
"""
import pytest
from typing import Dict, Any

from src.kuma_load.kuma_load import convert_time_range


def test_convert_time_range_no_timeRange_key():
    """Test that function returns unchanged dict when timeRange key is missing"""
    maintenance = {"title": "test", "enabled": True}
    result = convert_time_range(maintenance)
    assert result == maintenance
    assert result is maintenance  # Should return the same object


def test_convert_time_range_converts_single_time():
    """Test conversion of a single time range"""
    maintenance = {
        "title": "test",
        "timeRange": ["10:30:00"]
    }
    result = convert_time_range(maintenance)
    
    assert "timeRange" in result
    assert result["timeRange"] == [{"hours": 10, "minutes": 30, "seconds": 0}]


def test_convert_time_range_converts_multiple_times():
    """Test conversion of multiple time ranges"""
    maintenance = {
        "title": "test",
        "timeRange": ["09:15:45", "14:30:00", "23:59:59"]
    }
    result = convert_time_range(maintenance)
    
    assert len(result["timeRange"]) == 3
    assert result["timeRange"][0] == {"hours": 9, "minutes": 15, "seconds": 45}
    assert result["timeRange"][1] == {"hours": 14, "minutes": 30, "seconds": 0}
    assert result["timeRange"][2] == {"hours": 23, "minutes": 59, "seconds": 59}


def test_convert_time_range_handles_midnight():
    """Test conversion of midnight time"""
    maintenance = {
        "title": "test",
        "timeRange": ["00:00:00"]
    }
    result = convert_time_range(maintenance)
    
    assert result["timeRange"] == [{"hours": 0, "minutes": 0, "seconds": 0}]


def test_convert_time_range_preserves_other_fields():
    """Test that other fields are preserved"""
    maintenance = {
        "title": "test",
        "enabled": True,
        "timeRange": ["12:00:00"],
        "notes": "some notes"
    }
    result = convert_time_range(maintenance)
    
    assert result["title"] == "test"
    assert result["enabled"] is True
    assert result["notes"] == "some notes"
    assert result["timeRange"] == [{"hours": 12, "minutes": 0, "seconds": 0}]
