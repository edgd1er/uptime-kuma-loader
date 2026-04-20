import pytest

# adapter ces imports selon l'emplacement réel de la fonction et des constantes
from src.kuma_load import validate_monitor, ConfigError, REQUIRED_MONITOR_FIELDS, VALID_MONITOR_TYPES, VALID_AUTH_METHODS

# helper minimal valid monitor
def make_valid_monitor():
  # construire un monitor valide en supposant les champs requis incluent au moins "name" et "type"
  return {
    "name": "m1",
    "type": next(iter(VALID_MONITOR_TYPES)) if VALID_MONITOR_TYPES else "HTTP",
  }

def test_validate_monitor_accepts_minimal_valid():
  m = make_valid_monitor()
  # ne doit pas lever
  validate_monitor(m)

def test_validate_monitor_non_dict_raises():
  with pytest.raises(ConfigError, match="Monitor entry must be a table/object."):
    validate_monitor("not a dict")

def test_validate_monitor_missing_required_fields_raises():
  # construire dict vide -> missing includes required fields
  m = {}
  with pytest.raises(ConfigError) as exc:
    validate_monitor(m)
  assert "Missing required fields" in str(exc.value)

def test_validate_monitor_empty_name_raises():
  m = make_valid_monitor()
  m["name"] = "   "
  with pytest.raises(ConfigError, match="Field 'name' must be a non-empty string."):
    validate_monitor(m)

def test_validate_monitor_empty_type_raises():
  m = make_valid_monitor()
  m["type"] = "   "
  with pytest.raises(ConfigError):
    validate_monitor(m)

def test_validate_monitor_unknown_type_raises():
  m = make_valid_monitor()
  # choisir un type clairement invalide
  m["type"] = "UNKNOWN_TYPE_XYZ"
  with pytest.raises(ConfigError) as exc:
    validate_monitor(m)
  assert "unknown type" in str(exc.value)

def test_validate_monitor_invalid_auth_method_raises():
  m = make_valid_monitor()
  m["auth_method"] = "BAD_METHOD"
  with pytest.raises(ConfigError) as exc:
    validate_monitor(m)
  assert "invalid auth_method" in str(exc.value)

def test_validate_monitor_invalid_interval_type_raises():
  m = make_valid_monitor()
  m["interval"] = "60"
  with pytest.raises(ConfigError, match="'interval' must be integer seconds."):
    validate_monitor(m)

def test_validate_monitor_invalid_timeout_type_raises():
  m = make_valid_monitor()
  m["timeout"] = "10"
  with pytest.raises(ConfigError, match="'timeout' must be integer seconds."):
    validate_monitor(m)

def test_validate_monitor_invalid_port_type_raises():
  m = make_valid_monitor()
  m["port"] = "8080"
  with pytest.raises(ConfigError, match="'port' must be integer."):
    validate_monitor(m)

def test_validate_monitor_invalid_enabled_type_raises():
  m = make_valid_monitor()
  m["enabled"] = "true"
  with pytest.raises(ConfigError, match="'enabled' must be boolean."):
    validate_monitor(m)

def test_validate_monitor_invalid_tags_raises():
  m = make_valid_monitor()
  m["tags"] = ["a", 1]
  with pytest.raises(ConfigError, match="'tags' must be an array of strings."):
    validate_monitor(m)

def test_validate_monitor_invalid_notification_ids_raises():
  m = make_valid_monitor()
  m["notification_ids"] = [1, "2"]
  with pytest.raises(ConfigError, match="'notification_ids' must be an array of integers."):
    validate_monitor(m)

def test_validate_monitor_invalid_http_headers_raises():
  m = make_valid_monitor()
  m["http_headers"] = ["not", "a", "dict"]
  with pytest.raises(ConfigError, match="'http_headers' must be a table/dictionary."):
    validate_monitor(m)

def test_validate_monitor_http_basic_requires_username_and_password():
  m = make_valid_monitor()
  m["auth_method"] = "HTTP_BASIC"
  # missing username/password
  with pytest.raises(ConfigError) as exc:
    validate_monitor(m)
  assert "auth_method HTTP_BASIC requires 'username' and 'password'" in str(exc.value)

def test_validate_monitor_oauth2_cc_requires_keys():
  m = make_valid_monitor()
  m["auth_method"] = "OAUTH2_CC"
  # none of the oauth keys present
  with pytest.raises(ConfigError) as exc:
    validate_monitor(m)
  msg = str(exc.value)
  assert "auth_method OAUTH2_CC requires" in msg

def test_validate_monitor_full_valid_with_optional_fields():
  # construire monitor complet valide
  m = make_valid_monitor()
  m.update({
    "interval": 60,
    "timeout": 10,
    "port": 8080,
    "enabled": True,
    "tags": ["a", "b"],
    "notification_ids": [1, 2],
    "http_headers": {"X-Foo": "bar"},
  })
  # test pour auth HTTP_BASIC valide
  if "HTTP_BASIC" in VALID_AUTH_METHODS:
    m2 = dict(m)
    m2["auth_method"] = "HTTP_BASIC"
    m2["username"] = "u"
    m2["password"] = "p"
    validate_monitor(m2)
  # test pour OAUTH2_CC valide
  if "OAUTH2_CC" in VALID_AUTH_METHODS:
    m3 = dict(m)
    m3["auth_method"] = "OAUTH2_CC"
    m3["oauth2_token_url"] = "https://t"
    m3["oauth2_client_id"] = "id"
    m3["oauth2_client_secret"] = "secret"
    validate_monitor(m3)

