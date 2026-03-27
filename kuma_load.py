#!/usr/bin/env python3
import os
import random
import sys
import logging
import argparse
import importlib
from pathlib import Path
from typing import List, Dict, Any

# try tomllib (Py3.11+), otherwise tomli
try:
  tomllib = importlib.import_module("tomllib")
except Exception:
  try:
    tomllib = importlib.import_module("tomli")
  except Exception:
    print("Missing tomllib (Python 3.11+) or tomli. Install tomli with: pip install tomli")
    sys.exit(2)

try:
  from uptime_kuma_api import UptimeKumaApi, UptimeKumaException
except Exception:
  print('Missing UptimeKumaApi, pip install --break-system-packages uptime-kuma-api')


class ConfigError(Exception):
  pass


# variables
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())
# client = docker.from_env()
LDIR = os.path.dirname(os.path.realpath(__file__))

REQUIRED_MONITOR_FIELDS = {"name", "type"}
VALID_MONITOR_TYPES = {
  "group", "http", "port", "ping", "keyword", "json_query", "grpc_keyword", "dns", "docker",
  "real_browser", "push", "steam", "gamedig", "mqtt", "kafka_producer", "sqlserver", "postgres",
  "mysql", "mongodb", "radius", "redis", "tailscale_ping"
}
VALID_AUTH_METHODS = {"none", "http_basic", "ntlm", "mtls", "oauth2_cc"}


# functions
def get_token_from_kuma_api(kuma_api: UptimeKumaApi = None, username: str = '', password: str = '',
                            token: str = '') -> str:
  token = ''
  try:
    if token:
      result = kuma_api.login_by_token(token)
    elif username and password:
      result = kuma_api.login(username, password)
    token = result.get("token")
    logger.debug(f'token: {token}, result: {result}')
  except Exception as e:
    logger.error(f"Authentication error: {e}")
    kuma_api.disconnect()
    sys.exit(4)

  return token


def validate_monitor(m: Dict[str, Any]) -> None:
  if not isinstance(m, dict):
    raise ConfigError("Monitor entry must be a table/object.")
  missing = REQUIRED_MONITOR_FIELDS - set(m.keys())
  if missing:
    raise ConfigError(f"Missing required fields for monitor '{m.get('name', '<unknown>')}': {', '.join(missing)}")
  if not isinstance(m["name"], str) or not m["name"].strip():
    raise ConfigError("Field 'name' must be a non-empty string.")
  if not isinstance(m["type"], str) or not m["type"].strip():
    raise ConfigError(f"Monitor '{m['name']}': field 'type' must be a non-empty string.")
  if m["type"] not in VALID_MONITOR_TYPES:
    raise ConfigError(
      f"Monitor '{m['name']}': unknown type '{m['type']}'. Valid: {', '.join(sorted(VALID_MONITOR_TYPES))}")
  if "auth_method" in m:
    if not isinstance(m["auth_method"], str) or m["auth_method"] not in VALID_AUTH_METHODS:
      raise ConfigError(
        f"Monitor '{m['name']}': invalid auth_method '{m.get('auth_method')}'. Valid: {', '.join(sorted(VALID_AUTH_METHODS))}")
  if "interval" in m and not isinstance(m["interval"], int):
    raise ConfigError(f"Monitor '{m['name']}': 'interval' must be integer seconds.")
  if "timeout" in m and not isinstance(m["timeout"], int):
    raise ConfigError(f"Monitor '{m['name']}': 'timeout' must be integer seconds.")
  if "port" in m and not isinstance(m["port"], int):
    raise ConfigError(f"Monitor '{m['name']}': 'port' must be integer.")
  if "enabled" in m and not isinstance(m["enabled"], bool):
    raise ConfigError(f"Monitor '{m['name']}': 'enabled' must be boolean.")
  if "tags" in m:
    if not isinstance(m["tags"], list) or not all(isinstance(t, str) for t in m["tags"]):
      raise ConfigError(f"Monitor '{m['name']}': 'tags' must be an array of strings.")
  if "notification_ids" in m:
    if not isinstance(m["notification_ids"], list) or not all(isinstance(n, int) for n in m["notification_ids"]):
      raise ConfigError(f"Monitor '{m['name']}': 'notification_ids' must be an array of integers.")
  if "http_headers" in m and not isinstance(m["http_headers"], dict):
    raise ConfigError(f"Monitor '{m['name']}': 'http_headers' must be a table/dictionary.")
  # Additional basic checks for auth method related fields
  if m.get("auth_method") == "HTTP_BASIC":
    if "username" not in m or "password" not in m:
      raise ConfigError(f"Monitor '{m['name']}': auth_method HTTP_BASIC requires 'username' and 'password'.")
  if m.get("auth_method") == "OAUTH2_CC":
    for key in ("oauth2_token_url", "oauth2_client_id", "oauth2_client_secret"):
      if key not in m:
        raise ConfigError(f"Monitor '{m['name']}': auth_method OAUTH2_CC requires '{key}'.")


def load_toml(path: str) -> tuple[list | list[Any], list[Any] | Any]:
  with open(path, "rb") as f:
    data = tomllib.load(f)
  monitors = []
  notifications = []
  # support [[monitor]] tables
  if "monitor" in data and isinstance(data["monitor"], list):
    monitors = data["monitor"]
  elif "monitors" in data and isinstance(data["monitors"], list):
    monitors = data["monitors"]
  else:
    # support top-level array or single monitor table
    if isinstance(data, list):
      monitors = data
    else:
      if all(k in data for k in ("name", "type")):
        monitors = [data]
      else:
        raise ConfigError(
          "TOML must contain [[monitor]] tables, a top-level 'monitor(s)' array, or a single monitor table with 'name' and 'type'.")

  if "notification" in data and isinstance(data["notification"], list):
    notifications = data["notification"]

  if not isinstance(monitors, list) or not monitors:
    raise ConfigError("No monitors found in TOML file.")
  for m in monitors:
    validate_monitor(m)
  return monitors, notifications


def normalize_monitor_for_api(m: Dict[str, Any]) -> Dict[str, Any]:
  out = dict(m)  # shallow copy
  #out['type'] =f'MonitorType.{out["type"]}'
  # Convert http_headers entries if needed
  if "http_headers" in out and not isinstance(out["http_headers"], dict):
    headers = {}
    for item in out["http_headers"]:
      if isinstance(item, str) and "=" in item:
        k, v = item.split("=", 1)
        headers[k.strip()] = v.strip()
    out["http_headers"] = headers
  return out


def tags_needed(monitor: list[dict], existing_monitors: list[dict]) -> list[int]:
  logger.debug(f'existing_monitors tags: {existing_monitors["tags"]}')
  tags_to_add = [e for e in existing_monitors]
  for tag in monitor["tags"]:
    found_id = next((t['tag_id'] for t in existing_monitors["tags"] if t['tag_id'] == tag), None)
    logger.debug(f'tag: {tag}, id: {found_id}')
    tags_to_add.remove(found_id)
  logger.debug(f'tags_to_add: {tags_to_add}')
  return tags_to_add


def create_update_notification(api: UptimeKumaApi = None, config=None, dry_run: bool = False):
  if config is None:
    return {}
  kuma_notifications = api.get_notifications()
  payload = {'active': True, 'applyExisting': True, 'id': 1, 'isDefault': True, 'name': 'notification 1',
             'pushAPIKey': '123456789', 'type': 'PushByTechulus',
             'userId': 1}
  if config['name'] == kuma_notifications['name']:
    result = api.edit_notification(id_=config['name'], payload=payload)
  else:
    result = api.add_notification(payload=payload)

  logger.debug(f'result: {result}')


def process_notifications(api: UptimeKumaApi = None, existing_notifications: list[Dict[str, Any]] = None,
                          config_notifications: list[Dict[str, Any]] = None, delete: bool = False) -> dict[Any, dict[str, Any] | Any]:
  new_notifications = {}
  existing_notifications_names = {e['name']: e for e in existing_notifications}
  config_notifications_names = set(e['name'] for e in config_notifications)
  config_notifications_dict = {e['name']: e for e in config_notifications}
  logger.debug(f'existing_notifications: {existing_notifications}')
  logger.info(f'existing_notifications: {len(existing_notifications)}, names: {existing_notifications_names}')

  logger.debug(f'config_notifications: {config_notifications}')
  logger.info(f'config_notifications: {len(config_notifications)}, names: {config_notifications_names}')
  actions = {'added': [], 'edited': [], 'deleted': []}

  to_delete = set(existing_notifications_names.keys()) - config_notifications_names
  to_add = config_notifications_names - set(existing_notifications_names.keys())
  to_edit = config_notifications_names & set(existing_notifications_names.keys())

  logger.debug(f'notifications: deletion requested: {delete}, to_delete: {to_delete}, to_add: {to_add}')

  #add notification
  for n in to_add:
    payload = config_notifications[n]
    result = api.add_notification(**payload)
    #update current list of notifications
    existing_notifications[n] = {'name': n, 'id': result['monitorID']}
    logger.info(f"Created new notification '{n}', msg: {result['msg']}'")
    logger.debug(f"Created new notification '{n}',id :{result['monitorID']} , result: {result}")
    actions['added'].append(n)

  #edit notification
  for n in to_edit:
    payload = config_notifications_dict[n]
    existing_notification = existing_notifications_names[n]
    logger.debug(f"Edited notification '{n}', id: {existing_notification} ,payload: {payload}")
    result = api.edit_notification(id_=existing_notification['id'], **payload)
    logger.info(f"Edited notification '{n}', msg: {result['msg']}'")
    logger.debug(f"Edited notification '{n}', result: {result}")
    actions['edited'].append(n)

    #delete notifications
  if delete and len(to_delete) > 0:
    for n in to_delete:
      id = existing_notifications[n]['id']
      result = api.delete_notification(id_=n['id'])
      logger.info(f"Deleted group '{n}', id: '{id}', msg: {result['msg']}")
      logger.debug(f"Deleted new group '{n}, result: {result}'")
      #remove deleted group
      existing_notifications.pop(n)
      actions['deleted'].append(n)

  logger.debug(
    f'edited: {len(actions["edited"])}, {actions["edited"]}, added: {len(actions["added"])}, {actions["added"]}, deleted: {len(actions["deleted"])}, {actions["deleted"]}')
  return {n['name']: n for n in existing_notifications}


def process_groups(api: UptimeKumaApi = None, existing_groups=None, config_groups=None, delete: bool = False) -> dict:
  """
  create groups not present un kuma, delete groups not present in config
  :param delete:
  :param api:
  :param existing_groups:
  :param config_groups:
  :return:
  """

  added = []
  deleted = []
  # add missing groups first
  existing_group_names = [g for g in existing_groups]
  logger.debug(f'config_groups: {len(config_groups)}, config_groups: {config_groups}')
  logger.debug(f'existing_group_names: {len(existing_group_names)}, existing_group_names: {existing_group_names}')

  to_delete = set(existing_group_names) - set(config_groups)
  to_add = set(config_groups) - set(existing_group_names)

  logger.debug(f'deletion requested: {delete}, to_delete: {to_delete}, to_add: {to_add}')

  for g in to_add:
    payload = {'name': g, 'type': 'group'}
    result = api.add_monitor(**payload)
    #update current list of groups
    existing_groups[g] = {'name': g, 'id': result['monitorID']}
    logger.info(f"Created new group '{g}', msg: {result['msg']}'")
    logger.debug(f"Created new group '{g}', result: {result}")
    added.append(g)

  if delete and len(to_delete) > 0:
    for g in to_delete:
      id = existing_groups[g]['id']
      result = api.delete_monitor(id_=id)
      logger.info(f"Deleted group '{g}', id: '{id}', msg: {result['msg']}")
      logger.debug(f"Deleted new group '{g}, result: {result}'")
      #remove deleted group
      existing_groups.pop(g)
      deleted.append(g)

  logger.debug(f'added: {len(added)}, {added}, deleted: {len(deleted)}, {deleted}')
  return existing_groups


def import_config_into_kuma(file_path: str, api: UptimeKumaApi = None, dry_run: bool = False,
                            delete: bool = False) -> None:
  e, config_monitors, config_notifications = load_toml_config_file(file_path)
  if e is not None:
    logger.error(f"Failed to load monitors: {e}")
    sys.exit(4)
  if len(config_monitors) == 0 and len(config_notifications) == 0:
    logger.error(
      f"Empty monitors config ({len(config_monitors)}) or empty config_notifications ({len(config_notifications)})")
    sys.exit(4)

  existing_tags, existing_tags_id = get_tags(api)
  existing_config, existing_monitors = get_monitors(api)
  existing_groups = {g['name']: g for g in existing_config if 'group' == g['type']}
  logger.debug(f'existing_groups: {existing_groups}')
  logger.info(f'existing_groups: {len(existing_groups)}')

  # add/remove/edit Notifications
  existing_notifications = api.get_notifications()
  new_notifications = process_notifications(api=api, existing_notifications=existing_notifications,
                                            config_notifications=config_notifications, delete=delete)

  # add/remove Groups
  config_groups = set([g['group'] for g in config_monitors if 'group' in g.keys()])
  new_groups = process_groups(api=api, existing_groups=existing_groups, config_groups=config_groups, delete=delete)

  # Monitors
  for m in config_monitors:
    if m['type'] == "notification":
      result = create_update_notification(m)
    else:
      # then monitors
      logger.debug(f'monitor m: {m}')
      id_tags = []
      name = m["name"]
      monitor_toml_tags = m["tags"]
      # replace notification name with ids
      new_notification_ids_list = []
      for notif in m["notificationIDList"]:
        m["notificationIDList"].remove(notif)
        new_notification_ids_list.append(new_notifications[notif]['id'])
      m["notificationIDList"] = new_notification_ids_list
      payload = normalize_monitor_for_api(m)

      # add group if required
      if 'group' in m.keys():
        #add the new group id to current monitor, parent is the attribute name
        payload['parent'] = new_groups[m['group']]['id']
        logger.debug(f"adding parent '{m['group']}' to {name}")
      # group is not a monitor attribute
      payload.pop("group", None)

      # create missing tags in kuma
      tags_name_in_kuma = [t for t in existing_tags]
      logger.debug(f'tags_name: {tags_name_in_kuma}, monitor_toml_tags: {monitor_toml_tags}, existing_tags: {existing_tags}')

      for tag in monitor_toml_tags:
        if tag not in tags_name_in_kuma:
          result = api.add_tag(name=tag, color="#{:06x}".format(random.randint(0, 0xFFFFFF)))
          logger.info(f"tag created '{tag}'")
          logger.debug(f"tag created '{tag}', result: {result}")
          existing_tags[tag] = {'name': tag, 'id': result['id']}
      # add monitor does not accept tags,remove tags from payload, will be handled in process_existing_tags
      payload.pop("tags", None)

      if dry_run:
        if name in existing_monitors:
          logger.info(
            f"[DRY-RUN] Would update monitor '{name}' (id={existing_monitors[name]['id']}) with payload: {payload}")
        else:
          logger.info(f"[DRY-RUN] Would create monitor '{name}' with payload: {payload}")
        continue
      try:
        if name in existing_monitors:
          # update monitor
          mon_id = existing_monitors[name]["id"]
          logger.info(f"Updating monitor '{name}' (id={mon_id})...")
          logger.debug(f"Updating monitor '{name}' (id={mon_id})..., payload: {payload}")
          result = api.edit_monitor(mon_id, **payload)
          mon_id = result["monitorID"]
          result = api.get_monitor(id_=mon_id)
        else:
          # create monitor
          logger.info(f"Creating monitor '{name}'...")
          logger.debug(f"Creating monitor '{name}', payload: {payload}")
          result = api.add_monitor(**payload)
          mon_id = result["monitorID"]

      except Exception as e:
        logger.info(f"Error applying monitor '{name}': {e}")
        logger.debug(f"Error applying monitor '{name}', payload: {payload}, exception: {e}")

      logger.info("Import completed.")
      logger.debug(f'result: {result}, id_tags: {id_tags}')

      # handle tags
      process_existing_tags(api=api, monitor_id = mon_id, monitor=m, existing_tags=existing_tags)


# handle tags
def process_existing_tags(api:UptimeKumaApi = None, monitor_id:int = 0, monitor = None, existing_tags = None) -> None:
  """
  after monitor update, delete, add tags
  :param api:
  :param monitor:
  :param existing_tags:
  """
  if monitor == None or existing_tags is None:
    logger.warning(f'monitor or tags is none, nothing to proccess')

  # update tags list with updated existing tags
  tags_in_kuma = (next(iter(e)) for e in existing_tags)
  logger.debug(f'tags_in_config: {tags_in_kuma}')

  ids_to_add = []
  ids_to_delete = []

  kuma_monitor = api.get_monitor(id_=monitor_id)
  logger.debug(f'kuma_monitor: {kuma_monitor}')

  #get id of tags defined in kuma
  kuma_tags = []
  for t in kuma_monitor['tags']:
    kuma_tags.append(t['tag_id'])

  # ge id of tags in toml
  for t in monitor["tags"]:
    if existing_tags[t]['id'] not in tags_in_kuma:
      ids_to_add.append(existing_tags[t]['id'])
  logger.debug(f'ids_to_add: {ids_to_add}')

  #clean all defined tags to remove duplicate
  deleted = []
  for t in kuma_tags:
    # delete all association
    if t not in deleted:
      result = api.delete_monitor_tag(tag_id=t, monitor_id=monitor_id)
      logger.debug(f"Deleted tag '{t}' on monitor {monitor_id}")
      deleted.append(t)
    #tags association to recreate
    if t not in ids_to_add:
      ids_to_delete.append(t)

  logger.debug(f'ids_to_add: {ids_to_add}, ids_to_delete: {ids_to_delete}, kuma_tags: {kuma_tags}')
  # add tag-monitor association
  for i in ids_to_add:
    result = api.add_monitor_tag(tag_id=i, monitor_id=monitor_id)
    logger.info(f"Adding tag '{i}' to monitor {monitor_id}, result: {result['msg']}")
    logger.debug(f"Adding tag '{i}' to monitor {monitor_id}, result: {result}")

  # remove tag-monitor association.
  for i in ids_to_delete:
    if i not in deleted:
      result = api.delete_monitor_tag(tag_id=i, monitor_id=monitor_id)
      logger.info(f"Deleting tag '{i}' to monitor {monitor_id}, result: {result['msg']}")
      logger.debug(f"Deleting tag '{i}' to monitor {monitor_id}, result: {result}")

  #remove unused tags
  for d in deleted:
    if d not in ids_to_add:
      result = api.delete_tag(id_=d)
      logger.debug(f"Deleting tag '{i}', result: {result}")


def get_monitors(api: UptimeKumaApi | None) -> tuple[list[dict[Any, Any]], dict[str, dict]]:
  existing = {}
  try:
    existing_config = api.get_monitors()
    existing_monitors = {mon["name"]: mon for mon in existing_config if "name" in mon and "id" in mon}
    logger.debug(f'existing config: {existing_config}')
    logger.debug(f'existing config: {len(existing_config)}')
  except Exception as e:
    logger.error(f"Failed to fetch existing monitors: {e}")
    api.disconnect()
    sys.exit(5)
  return existing_config, existing_monitors


def get_tags(api: UptimeKumaApi | None) -> (list[dict()], list[int]):
  if api is None:
    return []
  existing_tags = []
  existing_tags_id = {}

  try:
    existing_tags = api.get_tags()
  except Exception as e:
    logger.error(f"Failed to get existing tags: {e}")
    sys.exit(5)

  unique_existing_tags = {}
  existing_tags_id = []
  seen = set()
  logger.debug(f'existing_tags: {[{e['name']: e} for e in existing_tags]}')
  for t in existing_tags:
    name = t.get('name')
    #logger.debug(f'name: {name}, t: {t}')
    if name not in seen:
      seen.add(name)
      unique_existing_tags[name] = t
      existing_tags_id.append(t['id'])

  logger.debug(f'unique tags: {unique_existing_tags}, existing_tags_id: {existing_tags_id}')

  return unique_existing_tags, existing_tags_id


def load_toml_config_file(file_path: str) -> tuple[Exception, list[dict[str, Any]], list[dict[str, Any]]]:
  e = None
  monitors = []
  notifications = []

  if not Path(file_path).is_file():
    logger.error(f"File path '{file_path}' not found.")
  try:
    monitors, notifications = load_toml(file_path)
  except (ConfigError, Exception) as e:
    logger.error(f"Configuration error: {e}")
  return e, monitors, notifications


def main():
  # set logger
  format = '%(asctime)s - %(levelname)s - %(name)s [%(funcName)s][%(lineno)d] - %(message)s'
  logging.basicConfig(format=format, level=logging.INFO)
  logger = logging.getLogger(__name__)
  logger.setLevel(logging.INFO)

  p = argparse.ArgumentParser(description="Import monitors from TOML into UptimeKuma via UptimeKumaApi")
  p.add_argument("--file", "-f", help="TOML file path", default="kuma.toml")
  p.add_argument("--api_url", "-a", help="UptimeKuma API URL or connection string", default="http://localhost:3001")
  p.add_argument("--username", "-u", help="API username", required=True)
  p.add_argument("--password", "-p", help="API password", required=True)
  p.add_argument("--token", "-t", help="API token (alternative to username/password)")
  p.add_argument("--dry-run", action="store_true", help="Don't call API; just display actions")
  p.add_argument("--verbose", "-v", help="mode verbose", default=False, action="store_true")
  p.add_argument("--delete", "-d", help="delete notifications, groups, monitors not defined in toml file",
                 default=False, action="store_true")
  args = p.parse_args()

  if args.username and not args.password:
    logger.error("When using --username you must provide --password.")
    sys.exit(1)
  if args.password and not args.username:
    logger.error("When using --password you must provide --username.")
    sys.exit(1)

  log_level = logging.DEBUG if args.verbose else logging.INFO
  logger.setLevel(log_level)

  ssl_true = True if args.api_url.startswith("https://") else False
  api = UptimeKumaApi(url=args.api_url, ssl_verify=ssl_true)

  if args.token:
    token = args.token
  else:
    token = get_token_from_kuma_api(kuma_api=api, username=args.username, password=args.password)

  logger.debug(f'token: {token}')

  result = api.get_database_size()
  logger.info(f'size: {result["size"]}')

  import_config_into_kuma(api=api, file_path=LDIR + os.sep + args.file, dry_run=args.dry_run, delete=args.delete)

  result = api.disconnect()
  logger.debug(f'result: {result}')


if __name__ == "__main__":
  main()
