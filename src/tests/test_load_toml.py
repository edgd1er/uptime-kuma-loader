import pytest
import tomli_w

from src.kuma_load.kuma_load import load_toml, ConfigError

# helper to write temporary toml files
def write_toml(tmp_path, content: bytes) -> str:
    p = tmp_path / "test.toml"
    p.write_bytes(content)
    return str(p)

def test_file_not_found():
    with pytest.raises(ConfigError) as exc:
        load_toml("nonexistent.toml")
    assert "TOML file not found" in str(exc.value)

def test_invalid_toml(tmp_path):
    path = write_toml(tmp_path, b"not = = toml")
    with pytest.raises(ConfigError) as exc:
        load_toml(path)
    assert "Invalid TOML" in str(exc.value)

def test_no_monitors(tmp_path):
    path = write_toml(tmp_path, tomli_w.dumps({"some": "value"}).encode("utf-8"))
    with pytest.raises(ConfigError) as exc:
        load_toml(path)
    assert "No monitors found" in str(exc.value)

def test_monitors_list_top_level(tmp_path, monkeypatch):
    content = {
      "name": "m1",
      "type": "http"}
    path = write_toml(tmp_path, tomli_w.dumps(content).encode("utf-8"))

    # stub validate_monitor so test focuses on parsing
    monkeypatch.setattr("src.kuma_load.kuma_load.validate_monitor", lambda m: None)

    docker, monitors, notifications, maintenances, statuses = load_toml(path)
    assert docker is None
    assert monitors == [content]
    assert notifications == []
    assert maintenances == []
    assert statuses == []

def test_monitors_under_monitor_key(tmp_path, monkeypatch):
    data = {"monitor": [{"name": "m", "type": "http"}], "notification": [{"a": 1}], "docker": [{"d": 1}], "maintenance": [{"mm": 1}]}
    path = write_toml(tmp_path, tomli_w.dumps(data).encode())

    monkeypatch.setattr("src.kuma_load.kuma_load.validate_monitor", lambda m: None)

    docker, monitors, notifications, maintenances, statuses = load_toml(path)
    assert monitors == data["monitor"]
    assert notifications == data["notification"]
    assert docker == data["docker"]
    assert maintenances == data["maintenance"]
    assert statuses == []

def test_single_monitor_table_shorthand(tmp_path, monkeypatch):
    # top-level dict with keys name and type should be treated as single monitor
    data = {"name": "solo", "type": "http"}
    path = write_toml(tmp_path, tomli_w.dumps(data).encode())

    monkeypatch.setattr("src.kuma_load.kuma_load.validate_monitor", lambda m: None)

    docker, monitors, notifications, maintenances, statuses = load_toml(path)
    assert monitors == [data]

def test_invalid_monitor_type(tmp_path, monkeypatch):
    # monitors list contains a non-dict entry -> ConfigError from validation in load_toml
    # Create a TOML with monitors as a list containing a non-dict (integer)
    data = {"monitors": [{"name": "ok", "type": "http"}, 123]}
    content = tomli_w.dumps(data).encode("utf-8")
    path = write_toml(tmp_path, content)

    # ensure validate_monitor won't mask the type check in load_toml
    monkeypatch.setattr("src.kuma_load.kuma_load.validate_monitor", lambda m: None)

    with pytest.raises(ConfigError) as exc:
        load_toml(path)
    assert "Each monitor must be a table/object" in str(exc.value)
