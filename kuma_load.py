#!/usr/bin/env python3
import os
import random
import sys
import logging
import argparse
import importlib
from pathlib import Path
from typing import List, Dict, Any, Counter
from unittest import result

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

  if "docker" in data and isinstance(data["notification"], list):
    docker = data["docker"]

  if not isinstance(monitors, list) or not monitors:
    raise ConfigError("No monitors found in TOML file.")
  for m in monitors:
    validate_monitor(m)
  return docker, monitors, notifications


def normalize_monitor_for_api(m: Dict[str, Any]) -> Dict[str, Any]:
  out = dict(m)  # shallow copy
  # out['type'] =f'MonitorType.{out["type"]}'
  # Convert http_headers entries if needed
  if "http_headers" in out and not isinstance(out["http_headers"], dict):
    headers = {}
    for item in out["http_headers"]:
      if isinstance(item, str) and "=" in item:
        k, v = item.split("=", 1)
        headers[k.strip()] = v.strip()
    out["http_headers"] = headers
  return out


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
                          config_notifications: list[Dict[str, Any]] = None, delete: bool = False) -> dict[
  Any, dict[str, Any] | Any]:
  new_notifications = {}
  existing_notifications_names = {e['name']: e for e in existing_notifications}
  config_notifications_names = {e['name'] for e in config_notifications}
  config_notifications_dict = {e['name']: e for e in config_notifications}
  logger.debug(f'existing_notifications: {existing_notifications}')
  logger.info(
    f'existing_notifications: {len(existing_notifications)}, names: {[e for e in existing_notifications_names.keys()]}')

  logger.debug(f'config_notifications: {config_notifications}')
  logger.info(f'config_notifications: {len(config_notifications)}, names: {[e for e in config_notifications_names]}')
  actions = {'added': [], 'edited': [], 'deleted': []}

  to_delete = set(existing_notifications_names.keys()) - config_notifications_names
  to_add = config_notifications_names - set(existing_notifications_names.keys())
  to_edit = config_notifications_names & set(existing_notifications_names.keys())

  logger.debug(f'notifications: deletion requested: {delete}, to_delete: {to_delete}, to_add: {to_add}')

  # add notification
  for n in to_add:
    payload = config_notifications[n]
    result = api.add_notification(**payload)
    # update current list of notifications
    existing_notifications[n] = {'name': n, 'id': result['monitorID']}
    logger.info(f"Created new notification '{n}', msg: {result['msg']}'")
    logger.debug(f"Created new notification '{n}',id :{result['monitorID']} , result: {result}")
    actions['added'].append(n)

  # edit notification
  for n in to_edit:
    payload = config_notifications_dict[n]
    existing_notification = existing_notifications_names[n]
    logger.debug(f"Edited notification '{n}', id: {existing_notification} ,payload: {payload}")
    result = api.edit_notification(id_=existing_notification['id'], **payload)
    logger.info(f"Edited notification '{n}', msg: {result['msg']}'")
    logger.debug(f"Edited notification '{n}', result: {result}")
    actions['edited'].append(n)

    # delete notifications
  if delete and len(to_delete) > 0:
    for n in to_delete:
      id = existing_notifications[n]['id']
      result = api.delete_notification(id_=n['id'])
      logger.info(f"Deleted group '{n}', id: '{id}', msg: {result['msg']}")
      logger.debug(f"Deleted new group '{n}, result: {result}'")
      # remove deleted group
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

  logger.info(f'deletion requested: {delete}, to_delete: {len(to_delete)}, to_add: {len(to_add)}')
  logger.debug(f'deletion requested: {delete}, to_delete: {to_delete}, to_add: {to_add}')

  for g in to_add:
    payload = {'name': g, 'type': 'group'}
    result = api.add_monitor(**payload)
    # update current list of groups
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
      # remove deleted group
      existing_groups.pop(g)
      deleted.append(g)

  logger.debug(f'added: {len(added)}, {added}, deleted: {len(deleted)}, {deleted}')
  return existing_groups


def process_docker_hosts(api: UptimeKumaApi = None, config_docker_hosts: Any = [], existing_docker_hosts: Any = [],
                         delete: bool = False) -> Any:
  if api is None:
    logger.error(f'api is none')
    sys.exit(4)

  new_existing_docker_hosts = {}
  existing_docker_hosts_ids = {d['name']: d for d in existing_docker_hosts}
  existing_names = existing_docker_hosts_ids.keys()
  config_docker_names = [d['name'] for d in config_docker_hosts]
  config_docker_hosts_ids = {d['name']: d for d in config_docker_hosts}
  to_add = set(config_docker_names) - set(existing_names)
  to_delete = existing_names - config_docker_names
  to_edit = config_docker_names & existing_names
  logger.debug(
    f'to_add: {len(to_add)}, {to_add}, to_delete: {len(to_delete)}, {to_delete}, to_edit: {len(to_edit)}, {to_edit}')
  logger.info(f'to_add: {len(to_add)}, to_delete: {len(to_delete)}, to_edit: {len(to_edit)}')
  added = []
  edited = []
  deleted = []

  for add_docker in to_add:
    temp = config_docker_hosts_ids[add_docker]
    result = api.add_docker_host(**temp)
    logger.debug(f'add_docker: {add_docker}, result: {result}')
    #logger.info(f'add_docker: {add_docker}, result: {result["msg"]}, nb: {api.test_docker_host(**result)}')
    added.append(add_docker)

  for edit_docker in to_edit:
    docker_id = existing_docker_hosts_ids[edit_docker]['id']
    result = api.edit_docker_host(id_=docker_id, **existing_docker_hosts_ids[edit_docker])
    payload = {"name": existing_docker_hosts_ids[edit_docker]['name'],
               "dockerType": existing_docker_hosts_ids[edit_docker]['dockerType'],
               "dockerDaemon": existing_docker_hosts_ids[edit_docker]['dockerDaemon']}
    logger.debug(f'edit_docker: {edit_docker}, result: {result}')
    #logger.info(f'edit_docker: {edit_docker}, result: {result["msg"]}, nb: {api.test_docker_host(**payload)}')
    edited.append(edit_docker)

  if delete and len(to_delete) > 0:
    for delete_docker in to_delete:
      docker_id = existing_docker_hosts_ids[delete_docker]['id']
      result = api.delete_docker_host(id_=docker_id)
      logger.debug(f'delete_docker: {delete_docker}, result: {result}')
      logger.info(f'delete_docker: {delete_docker}, result: {result["msg"]}')
      deleted.append(delete_docker)

  logger.info(f'added: {len(added)}, edited: {len(edited)}, deleted: {len(deleted)}')
  logger.debug(f'added: {added}, edited: {edited}, deleted: {deleted}')

  return api.get_docker_hosts()


def add_remove_tags(api: UptimeKumaApi = None, existing_tags: Dict[str, Any] = None, config_tags: list[str] = None,
                    delete: bool = False):
  """
  add missing tags, delete not used tags, delete duplicates.

  :param api:
  :param existing_tags: tags found in kuma
  :param config_tags: tags found in toml
  :param delete: if true delete tags from kuma
  :return:
  """

  logger.debug(f'existing_monitors tags: {existing_tags}')
  existing_tag_names = [t['name'] for t in existing_tags]
  to_add = set(config_tags) - set(existing_tag_names)
  to_delete = set(existing_tag_names) - set(config_tags)
  logger.debug(f'tags to_add: {to_add}, to_delete: {to_delete}')
  logger.info(f'tags to_add: {len(to_add)}, to_delete: {len(to_delete)}')

  # remove duplicate monitors
  c = Counter(existing_tag_names)
  logger.debug(f'counter: {c}')
  duplicates = {k: v for k, v in c.items() if v > 1}
  logger.info(f'duplicate tags found: {duplicates}')

  added = []
  deleted = []

  for tag in to_add:
    result = api.add_tag(name=tag, color="#{:06x}".format(random.randint(0, 0xFFFFFF)))
    logger.info(f"tag created '{tag}'")
    logger.debug(f"tag created '{tag}', result: {result}")
    existing_tags.append(result)
    added.append(tag)

  if delete:
    if len(duplicates) > 0:
      for k, v in duplicates.items():
        logger.debug(f"tag to delete '{k}' {v - 1} times")
        for i in range(v - 1):
          for idx, tag in enumerate(existing_tags):
            if tag['name'] == k:
              id = tag['id']
              try:
                result = api.delete_tag(id_=id)
              except Exception as e:
                logger.error(f'{e}')
              logger.debug(f"tag deleted '{tag['name']}={v}', id: {id}, result: {result}'")
              existing_tags.pop(idx)
              break

    if len(to_delete) > 0:
      for delete_tag in to_delete:
        tag_id = [e['id'] for e in existing_tags if e['name'] == delete_tag].pop(0)
        try:
          result = api.delete_tag(id_=tag_id)
          logger.info(f"tag deleted '{delete_tag}, id:{tag_id}', result: {result['msg']}")
          logger.debug(f"tag deleted '{delete_tag}', result: {result}")
          deleted.append(delete_tag)
          existing_tags.pop(delete_tag)
        except Exception as e:
          logger.error(f'delete tag {delete_tag}: {e}')

  logger.info(f'added: {len(added)}, deleted: {len(deleted)}')
  logger.debug(f'added: {added}, deleted: {deleted}')

  return existing_tags


def replace_tag_names_with_id(config_tags: list[str], existing_tags: Dict[str, Any]) -> list[int]:
  tags_id = []
  for ctag in config_tags:
    for d in existing_tags:
      if d['name'] == ctag:
        tags_id.append(d['id'])

  tags_id2 = [d['id'] for ctag in config_tags for d in existing_tags if d['name'] == ctag]
  logger.debug(f'tags_id2: {tags_id2}, tags_id: {tags_id}')
  return tags_id


def import_config_into_kuma(file_path: str, api: UptimeKumaApi = None, dry_run: bool = False,
                            delete: bool = False) -> None:
  e, config_docker_hosts, config_monitors, config_notifications = load_toml_config_file(file_path)
  if e is not None:
    logger.error(f"Failed to load monitors: {e}")
    sys.exit(4)
  if len(config_monitors) == 0 and len(config_notifications) == 0:
    logger.error(
      f"Empty monitors config ({len(config_monitors)}) or empty config_notifications ({len(config_notifications)})")
    sys.exit(4)

  existing_config, existing_monitors = get_monitors(api)
  existing_groups = {g['name']: g for g in existing_config if 'group' == g['type']}
  logger.debug(f'existing_groups: {existing_groups}')
  logger.info(f'existing_groups: {len(existing_groups)}')

  # add/remove tags
  existing_tags, existing_tags_id = get_tags(api)
  config_tags = []
  for c in config_monitors:
    if "tags" in c.keys():
      config_tags.extend(c['tags'])
  # unique list
  config_tags = list(set(config_tags))
  new_tags = add_remove_tags(api=api, existing_tags=existing_tags, config_tags=config_tags, delete=delete)
  new_tags_id = {t['name']: t for t in new_tags}

  # add/remove/edit Notifications
  existing_notifications = api.get_notifications()
  new_notifications = process_notifications(api=api, existing_notifications=existing_notifications,
                                            config_notifications=config_notifications, delete=delete)

  # add/remove Groups
  config_groups = set([g['group'] for g in config_monitors if 'group' in g.keys()])
  new_groups = process_groups(api=api, existing_groups=existing_groups, config_groups=config_groups, delete=delete)

  # add/edit/remove docker_hosts
  existing_docker_hosts = api.get_docker_hosts()
  new_docker_hosts = process_docker_hosts(api=api,config_docker_hosts=config_docker_hosts, existing_docker_hosts=existing_docker_hosts, delete=delete)
  # replace docker_host by id if string found
  for c in config_monitors:
    if "docker_host" in c.keys():
      name_docker = c['docker_host']
      if isinstance(name_docker, str):
          c['docker_host'] = ([ dh['id'] for dh in new_docker_hosts if dh['name'] == name_docker ][0])

  # add/edit/delete containers

  # Look for duplicate monitor and delete them if required
  existing_monitor_ids = [existing_monitors[e]['id'] for e in existing_monitors]
  # groups are returned with monitors, filtering them out
  existing_monitor_names = [existing_monitors[e]['name'] for e, v in existing_monitors.items() if v['type'] != 'group']
  config_monitor_names = [e['name'] for e in config_monitors]

  to_delete = set(existing_monitor_names) - set(config_monitor_names)
  to_add = set(config_monitor_names) - set(existing_monitor_names)
  to_edit = set(config_monitor_names) & set(existing_monitor_names)
  c = Counter(existing_monitor_names)

  # remove duplicate monitors
  # logger.debug(f'counter: {c}')
  duplicates = [k for k, v in c.items() if v > 1]
  logger.debug(f'duplicates found: {duplicates}')
  # c = Counter([e for e in existing_monitors])

  logger.debug(
    f'monitor to_add: {len(to_add)}, {to_add}, to_delete: {len(to_delete)}, {to_delete}, to_edit: {len(to_edit)}, {to_edit}')
  logger.info(f'monitor to_add: {len(to_add)}, to_delete: {len(to_delete)}, to_edit: {len(to_edit)}')
  added = []
  edited = []
  deleted = []

  if delete and len(to_delete) > 0:
    for elt in to_delete:
      id = [v['id'] for k, v in existing_monitors.items() if k == elt][0]
      result = api.delete_monitor(id_=id)
      logger.info(f"Deleting removed monitor '{elt}', id={id}, result: {result['msg']}")
      logger.debug(f"Deleting removed monitor '{elt}', id={id}, result: {result}")
  #   mon_id = elt['id']
  #   name = elt['name']
  #   if mon_id not in existing_monitor_ids:
  #     logger.warning(f'Duplicate found: {name}, id: {mon_id}')
  #     existing_config.remove(elt)
  #     if delete:
  #       result = api.delete_monitor(id_=int(mon_id))
  #       logger.info(f"Deleting duplicate monitor '{name}', id={mon_id}, result: {result['msg']}")
  #       logger.debug(f"Deleting duplicate monitor '{name}', id={mon_id}, result: {result}")

  # Monitors
  monitor_processed = []
  for m in config_monitors:
    if m['type'] == "notification":
      result = create_update_notification(m)
    else:
      # then monitors
      logger.debug(f'monitor m: {m}')
      id_tags = []
      mon_id = None
      name = m["name"]
      monitor_toml_tags = m["tags"] if "tags" in m.keys() else []
      # replace notification name with ids
      new_notification_ids_list = []
      if "notificationIDList" in m.keys():
        for notif in m["notificationIDList"]:
          m["notificationIDList"].remove(notif)
          new_notification_ids_list.append(new_notifications[notif]['id'])
        m["notificationIDList"] = new_notification_ids_list
      else:
        m["notificationIDList"] = []
      payload = normalize_monitor_for_api(m)

      # add group if required
      if 'group' in m.keys():
        # add the new group id to current monitor, parent is the attribute name
        payload['parent'] = new_groups[m['group']]['id']
        logger.debug(f"adding parent '{m['group']}' to {name}")
      # group is not a monitor attribute
      payload.pop("group", None)

      if dry_run:
        if name in existing_monitors:
          logger.info(
            f"[DRY-RUN] Would update monitor '{name}' (id={existing_monitors[name]['id']}) with payload: {payload}")
        else:
          logger.info(f"[DRY-RUN] Would create monitor '{name}' with payload: {payload}")
        continue

      # save tags for later, remove from payloads as tag are traeted separately
      if "tags" in payload.keys():
        payload_tags = payload['tags']
          #replace_tag_names_with_id(payload['tags'], existing_tags))
        payload.pop("tags", None)
      else:
        payload_tags = []

      # update monitor
      if name in existing_monitors:
        mon_id = existing_monitors[name]["id"]
        try:
          result = api.edit_monitor(mon_id, **payload)
          logger.info(f"Updating monitor '{name}', id={mon_id}, result: {result['msg']}")
          logger.debug(f"Updating monitor '{name}', id={mon_id}, result: {result}, payload: {payload}")
          mon_id = result["monitorID"]
          monitor_processed.append(name)
          kuma_monitor = api.get_monitor(id_=mon_id)
        except Exception as e:
          logger.error(f"Error updating monitor '{name}': {e}")
          logger.debug(f"Error updating monitor '{name}', payload: {payload}, exception: {e}")
      else:
        # create monitor
        try:
          result = api.add_monitor(**payload)
          logger.info(f"Creating monitor '{name}', id={mon_id}, result: {result['msg']}")
          logger.debug(f"Creating monitor '{name}', id={mon_id}, result: {result}, payload: {payload}")
          mon_id = result["monitorID"]
          kuma_monitor = api.get_monitor(id_=mon_id)
        except Exception as e:
          logger.error(f"Error creating monitor '{name}': {e}")
          logger.debug(f"Error creating monitor '{name}', payload: {payload}, exception: {e}")

      logger.info(f"Import completed for '{name}'.")
      # handle tags
      # restore tags from config
      m['tags'] = payload_tags
      update_monitor_tags(api=api, monitor_id=mon_id, monitor=m, kuma_monitor=kuma_monitor, existing_tags=new_tags_id,
                          delete=delete)
      logger.debug(f'result: {result}, id_tags: {id_tags}')


# handle tags
def update_monitor_tags(api: UptimeKumaApi = None, monitor_id: int = 0, monitor=None, kuma_monitor=None,
                        existing_tags=None, delete: bool = False) -> None:
  """
  after monitor update, add tag association if missing.
  :param monitor_id:
  :param api:
  :param monitor:
  :param existing_tags:
  :param delete:
  """
  if monitor == None or existing_tags is None or monitor_id is None or monitor_id == 0:
    logger.warning(f'monitor or tags or id is none, nothing to proccess')
    return

  # replace tags by id if tags key is present
  add_tags = []
  # if monitor tags has a list of tags defined
  if len(monitor['tags']) > 0 and isinstance(monitor['tags'], list):
    # if string, convert to full tag structure
    if all(isinstance(x, str) for x in monitor['tags']):
      logger.debug(f'tags: {monitor['tags']}')
      # check for duplicates, get id from existing tags
      tags2 = [v['id'] for k in monitor['tags'] for c, v in existing_tags.items() if c == k]
      for tag in monitor['tags']:
        add_tags.extend([v['id'] for t, v in existing_tags.items() if t == tag])

    # full structure for an edited monitor
    if all(isinstance(x, dict) for x in monitor['tags']):
      add_tags = set(add_tags) - set([k['tag_id'] for k in monitor['tags']])

    # if int, already
    if all(isinstance(x, int) for x in monitor['tags']):
      add_tags.extend(monitor['tags'])


  # use a counter for duplicates identification
  duplicates = {k: v for k, v in Counter(add_tags).items() if v > 1}
  if len(duplicates) > 0:
    logger.info(f"Duplicate tags found: {duplicates}")
  add_tags = set(add_tags)

  # tags to remove
  delete_tags = [t['tag_id'] for t in kuma_monitor['tags'] if t['tag_id'] not in existing_tags]
  # duplicate tags
  c = Counter([k['tag_id'] for k in kuma_monitor['tags']])
  duplicates_to_remove = {k: v for k, v in c.items() if v > 1}
  if len(duplicates_to_remove) > 0:
    logger.info(f'duplicate tags found: {duplicates_to_remove}')
  if delete:
    for k, v in duplicates_to_remove.items():
      result = api.delete_monitor_tag(tag_id=k, monitor_id=monitor_id)
      logger.info(f'delete duplicate monitor tag: {k}={v}, result: {result['msg']}')
      logger.debug(f'delete duplicate monitor tag: {k}={v}, result: {result}')

    for d in delete_tags:
      if d not in add_tags:
        result = api.delete_monitor_tag(tag_id=d, monitor_id=monitor_id)
        logger.info(f"Deleting tag '{d}' to monitor {monitor_id}, result: {result['msg']}")
        logger.debug(f"Deleting tag '{d}' to monitor {monitor_id}, result: {result}")

  #
  for tag in add_tags:
    if tag not in [ k['tag_id'] for k in kuma_monitor['tags']]:
      try:
        result = api.add_monitor_tag(tag_id=tag, monitor_id=monitor_id)
        logger.info(f"Adding tag '{tag}' to monitor {monitor_id}, result: {result['msg']}")
        logger.debug(f"Adding tag '{tag}' to monitor {monitor_id}, result: {result}")
      except Exception as e:
        logger.error(f'error adding tag {tag} to monitor {monitor_id}: {e}')


def get_monitors(api: UptimeKumaApi | None) -> tuple[list[dict[Any, Any]], dict[str, dict]]:
  """
  return monitors in kuma (existing_config) and rebuild a dictionay with monitor name as key (existing_monitors)
  :param api:
  :return:
  """
  existing = {}
  try:
    existing_config = api.get_monitors()
    existing_monitors = {mon["name"]: mon for mon in existing_config if "name" in mon and "id" in mon}
    logger.debug(f'existing config: len: {len(existing_config)}, {existing_config}')
    logger.debug(f'existing monitors: len: {len(existing_monitors)}, {existing_monitors}')
  except Exception as e:
    logger.error(f"Failed to fetch existing monitors: {e}")
    api.disconnect()
    sys.exit(5)
  return existing_config, existing_monitors


def get_tags(api: UptimeKumaApi | None) -> list[Any] | tuple[list[Any], dict[Any, dict]]:
  if api is None:
    return []
  existing_tags = []
  existing_tags_id = {}

  try:
    existing_tags = api.get_tags()
  except Exception as e:
    logger.error(f"Failed to get existing tags: {e}")
    sys.exit(5)

  existing_tag_names = list([t['name'] for t in existing_tags])
  existing_tags_id = {t['id']: t for t in existing_tags}

  logger.info(f'existing_tags: {len(existing_tags)}, existing_tags_id: {len(existing_tags_id.keys())}')
  logger.debug(f'existing_tags:  {[v['name'] for k, v in existing_tags_id.items()]}')

  logger.debug(f'unique tags: {existing_tags}, existing_tags_id: {existing_tags_id}')

  return existing_tags, existing_tags_id


def load_toml_config_file(file_path: str) -> tuple[
  Exception, list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
  e = None
  monitors = []
  notifications = []
  docker = []

  if not Path(file_path).is_file():
    logger.error(f"File path '{file_path}' not found.")
  try:
    docker, monitors, notifications = load_toml(file_path)
  except (ConfigError, Exception) as e:
    logger.error(f"Configuration error: {e}")
    sys.exit(1)
  return e, docker, monitors, notifications


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
  logger.info(f'Database size: {result["size"]}')
  result = api.need_setup()
  logger.info(f'need setup: {result}')
  result = api.info()
  logger.info(f'info: {result}')
  # result = api.uptime()
  # logger.info(f'uptime: {result}')

  import_config_into_kuma(api=api, file_path=LDIR + os.sep + args.file, dry_run=args.dry_run, delete=args.delete)

  result = api.disconnect()
  logger.debug(f'result: {result}')


if __name__ == "__main__":
  main()
