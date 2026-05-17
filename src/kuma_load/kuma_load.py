#!/usr/bin/env python3
import os
import random
import sys
import logging
import argparse
import importlib
from pathlib import Path
from typing import List, Dict, Any, Counter, LiteralString, Tuple, Optional

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
CDIR = os.getcwd()

REQUIRED_MONITOR_FIELDS = {"name", "type"}
VALID_MONITOR_TYPES = {
  "group", "http", "port", "ping", "keyword", "json_query", "grpc_keyword", "dns", "docker",
  "real_browser", "push", "steam", "gamedig", "mqtt", "kafka_producer", "sqlserver", "postgres",
  "mysql", "mongodb", "radius", "redis", "tailscale_ping"
}
VALID_AUTH_METHODS = {"none", "http_basic", "ntlm", "mtls", "oauth2_cc"}


# functions
def fix_api():
  #api L"incident": r2["incident"], - W  #"incident": r2["incidents"],
  #api LL2173: status_page.pop("maintenanceList"), add status_page.pop("autoRefreshInterval")
  #analyticsId
  #data.pop('analyticsId')


  pass
def get_token_from_kuma_api(kuma_api: "UptimeKumaApi",
                            username: str = "",
                            password: str = "",
                            token: str = "") -> Optional[str]:
  """
  Retourne un token valide en utilisant, dans l'ordre :
  - le token donné (si non vide) via login_by_token
  - sinon username/password via login
  Retourne None en cas d'échec.
  """
  if kuma_api is None:
    logger.error("kuma_api is None")
    return None

  try:
    if token:
      result = kuma_api.login_by_token(token)
    elif username and password:
      result = kuma_api.login(username, password)
    else:
      logger.error("No credentials provided (token or username+password)")
      return None

    tok = result.get("token")
    if not tok:
      logger.error("Authentication succeeded but no token returned")
      return None

    logger.debug("Authentication result: %s", result)
    return tok

  except Exception as e:
    logger.exception("Authentication error")
    # ne pas faire sys.exit ici : laisser l'appelant gérer l'arrêt
    try:
      kuma_api.disconnect()
    except Exception:
      logger.info("kuma_api.disconnect() failed", exc_info=False)
      logger.debug("kuma_api.disconnect() failed", exc_info=True)
    return None


def validate_monitor(m: Dict[str, Any]) -> None:
  """
  Check monitor against an expected structure
  :param m:
  """
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
    if not isinstance(m["auth_method"], str) or m["auth_method"].lower() not in VALID_AUTH_METHODS:
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


def load_toml(path: str) -> Tuple[
  Optional[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
  try:
    with open(path, "rb") as f:
      data = tomllib.load(f)
  except FileNotFoundError:
    raise ConfigError(f"TOML file not found: {path}")
  except tomllib.TOMLDecodeError as e:
    raise ConfigError(f"Invalid TOML: {e}") from e

  docker: Optional[Dict[str, Any]] = None
  monitors: List[Dict[str, Any]] = []
  notifications: List[Dict[str, Any]] = []
  maintenances: List[Dict[str, Any]] = []
  statuses: List[Dict[str, Any]] = []

  # monitors: prefer explicit tables/arrays, else single top-level table or array
  if isinstance(data, list):
    monitors = data
  else:
    if isinstance(data.get("monitor"), list):
      monitors = data["monitor"]
    elif isinstance(data.get("monitors"), list):
      monitors = data["monitors"]
    elif all(k in data for k in ("name", "type")) and isinstance(data, dict):
      monitors = [data]

  if not monitors:
    raise ConfigError("No monitors found in TOML file.")

  # notifications
  if isinstance(data.get("notification"), list):
    notifications = data["notification"]

  # docker
  if isinstance(data.get("docker"), list):
    docker = data["docker"]

  # maintenances
  if isinstance(data.get("maintenance"), list):
    maintenances = data["maintenance"]

  # statuses
  if isinstance(data.get("status"), list):
    statuses = data["status"]

  for m in monitors:
    if not isinstance(m, dict):
      raise ConfigError("Each monitor must be a table/object")
    validate_monitor(m)

  return docker, monitors, notifications, maintenances, statuses


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


# -----------------------------------------------------------
# TODO Test
def process_notifications(api: "UptimeKumaApi" = None, existing_notifications: list[Dict[str, Any]] = None,
                          config_notifications: list[Dict[str, Any]] = None, delete: bool = False) -> dict[
  Any, dict[str, Any] | Any]:
  new_notifications = {}
  existing_notifications_names = [e['name'] for e in existing_notifications]
  existing_notifications_dict = {e['name']: e for e in existing_notifications}
  config_notifications_names = {e['name'] for e in config_notifications}
  config_notifications_dict = {e['name']: e for e in config_notifications}
  logger.debug(f'existing_notifications: {existing_notifications}')
  logger.info(
    f'existing_notifications: {len(existing_notifications)}, names: {[e for e in existing_notifications_dict.keys()]}')

  logger.debug(f'config_notifications: {config_notifications}')
  logger.info(f'config_notifications: {len(config_notifications)}, names: {[e for e in config_notifications_names]}')
  actions = {'added': [], 'edited': [], 'deleted': []}

  to_delete = set(existing_notifications_dict.keys()) - config_notifications_names
  to_add = config_notifications_names - set(existing_notifications_dict.keys())
  to_edit = config_notifications_names & set(existing_notifications_dict.keys())

  c = Counter(existing_notifications_names)
  duplicates = [k for k, v in c.items() if v > 1]
  for i in duplicates:
    to_delete.add(i)
  logger.debug(f'notifications: deletion requested: {delete}, to_delete: {to_delete}, to_add: {to_add}')

  # add notification
  for n in to_add:
    payload = config_notifications_dict[n]
    result = api.add_notification(**payload)
    # update current list of notifications
    existing_notifications_dict[n] = {'name': n, 'id': result['id']}
    logger.info(f"Created new notification '{n}', msg: {result['msg']}'")
    logger.debug(f"Created new notification '{n}',id :{result['id']} , result: {result}")
    actions['added'].append(n)

  # edit notification
  for n in to_edit:
    payload = config_notifications_dict[n]
    existing_notification = existing_notifications_dict[n]
    logger.debug(f"Edited notification '{n}', id: {existing_notification} ,payload: {payload}")
    result = api.edit_notification(id_=existing_notification['id'], **payload)
    logger.info(f"Edited notification '{n}', msg: {result['msg']}'")
    logger.debug(f"Edited notification '{n}', result: {result}")
    actions['edited'].append(n)

    # delete notifications
  if delete and len(to_delete) > 0:
    for n in to_delete:
      id = existing_notifications_dict[n]['id']
      result = api.delete_notification(id_=id)
      logger.info(f"Deleted group '{n}', id: '{id}', msg: {result['msg']}")
      logger.debug(f"Deleted new group '{n}, result: {result}'")
      # remove deleted group
      existing_notifications_dict.pop(n)
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


def process_docker_hosts(
        api: "UptimeKumaApi",
        config_docker_hosts: Optional[List[Dict[str, Any]]] = None,
        existing_docker_hosts: Optional[List[Dict[str, Any]]] = None,
        delete: bool = False,
) -> List[Dict[str, Any]]:
  if api is None:
    raise ValueError("api must not be None")

  config = config_docker_hosts or []
  existing = existing_docker_hosts or []

  # Validate inputs
  if not isinstance(config, list) or not isinstance(existing, list):
    raise TypeError("config_docker_hosts and existing_docker_hosts must be lists")

  # Index by name and by id for convenience
  existing_by_name = {d['name']: d for d in existing}
  existing_by_id = {d['id']: d for d in existing}
  config_by_name = {d['name']: d for d in config}

  config_names = set(config_by_name.keys())
  existing_names = set(existing_by_name.keys())

  to_add = config_names - existing_names
  to_delete = existing_names - config_names
  to_edit = config_names & existing_names

  added, edited, deleted = [], [], []

  # Add new docker hosts
  for name in to_add:
    payload = config_by_name[name]
    try:
      result = api.add_docker_host(**payload)
      added.append(name)
      logger.info("Added docker host %s", name)
      logger.debug("add result: %s", result)
    except Exception:
      logger.exception("Failed to add docker host %s", name)

  # Edit existing docker hosts
  for name in to_edit:
    existing_entry = existing_by_name[name]
    docker_id = existing_entry['id']
    # we should send desired config (from config), not existing entry
    payload = config_by_name[name]
    try:
      result = api.edit_docker_host(id_=docker_id, **payload)
      edited.append(name)
      logger.info("Edited docker host %s (id=%s)", name, docker_id)
      logger.debug("edit result: %s", result)
    except Exception:
      logger.exception("Failed to edit docker host %s (id=%s)", name, docker_id)

  # Delete removed docker hosts (only if delete requested)
  if delete:
    for name in to_delete:
      entry = existing_by_name[name]
      docker_id = entry['id']
      try:
        result = api.delete_docker_host(id_=docker_id)
        deleted.append(name)
        logger.info("Deleted docker host %s (id=%s)", name, docker_id)
        logger.debug("delete result: %s", result)
      except Exception:
        logger.exception("Failed to delete docker host %s (id=%s)", name, docker_id)

  logger.info("added=%d edited=%d deleted=%d", len(added), len(edited), len(deleted))
  logger.debug("added=%s edited=%s deleted=%s", added, edited, deleted)

  return api.get_docker_hosts()


def process_status_pages(api: 'UptimeKumaApi' = None, config_status_pages: Dict[str, Any] = None,
                         delete: bool = False) -> List[Dict[str, Any]]:
  if api is None:
    raise ValueError("api must not be None")

  config = config_status_pages or []

  existing_status_pages = []
  try:
    existing_status_pages = api.get_status_pages()
  except Exception as e:
    logger.error(f'get_status_pages: {e}')

  if len(existing_status_pages) == 0 and len(config_status_pages) == 0:
    return []

  to_add = set({s['slug'] for s in config}) - set({s['slug'] for s in existing_status_pages})
  to_edit = set({s['slug'] for s in config}) & set({s['slug'] for s in existing_status_pages})
  to_delete = set({s['slug'] for s in existing_status_pages}) - set({s['slug'] for s in config})

  config_by_names = {c['slug']: c for c in config}
  existing_status_pages_names = {e['slug']: e for e in existing_status_pages}

  _, monitor_names = get_monitors(api)

  for d in to_delete:
    try:
      slug = existing_status_pages_names[d].get('slug')
      ret = api.delete_status_page(slug=slug)
      if ret == {}:
        logger.info(f"Deleted status page {slug}")
        logger.debug(f"Deleted status page {slug}, ret: {ret}")
      else:
        logger.info(f"Error on deletion status page {slug}")
        logger.debug(f"Error on deletion status page {slug}, ret: {ret}")

    except Exception as e:
      logger.info(f'Error deleting status page {slug}')
      logger.debug(f'Error deleting status page {slug}: {e}')

  for a in to_add:
    try:
      ret = api.add_status_page(slug=config_by_names[a]['slug'], title=config_by_names[a].get('title'))
      logger.info(f"Added status page {config_by_names[a]['slug']}: {ret['msg']}")
      logger.debug(f"Added status page {config_by_names[a]['slug']}: {ret}")
      # TODO complete processing
      ret = api.save_status_page(slug= config_by_names[a]['slug'],**config_status_pages)
    except Exception as e:
      logger.info(f'Error adding status page {config_by_names[a]["title"]}')
      logger.debug(f'Error adding status page {config_by_names[a]["title"]}: {e}')
      sys.exit()

  for e in to_edit:
    id = existing_status_pages_names[e].get('id')
    edited = config_by_names[e]
    edited['id'] = id

    #
    pgl = edited.get('publicGroupList', None)
    # is publicGroupList present ?
    if pgl is not None:
      # for all monitors found
      for idx_pgl, l in enumerate(pgl):
        # replace monitor names with id
        for idx_m, m in enumerate(l['monitorList']):
          if 'id' not in m.keys():
            logger.warning(f'status page {edited["title"]}, improper monitorList structure, missing id: {m}')
            continue

          name = m.get('id', None)
          if name in monitor_names.keys():
            # find id corresponding to the name
            id = monitor_names[name].get('id', None)
            if id is None:
              logger.warning(f'status page {edited["title"]}, id not found for monitor {name} existing configs.')
            m['id'] = id
          else:
            logger.warning(f'status page {edited["title"]}, monitor {name} not found in existing configs')
            m['id'] = None

        # Filter out empty dict.
        temp_list = l['monitorList']
        l['monitorList'] = [e for e in temp_list if e.get('id', None) is not None]

    logger.debug(f'edited pgl: {pgl}')

    # remove autoRefreshInterval
    try:
      ret = api.save_status_page(**edited)
      logger.info(f"Added status page {edited['slug']}: {ret}")
      logger.debug(f"Added status page {edited['slug']}: {ret}")
    except Exception as e:
      logger.info(f'Error adding status page {edited["title"]}({edited["id"]})')
      logger.debug(f'Error adding status page {edited["title"]}({edited["id"]}: {e}')
      sys.exit()


  for s in existing_status_pages:
      logger.info(f's: {s}')


def add_remove_tags(api: 'UptimeKumaApi' = None, config_monitors: Dict[str, Any] = None, delete: bool = False):
  """
  add missing tags, delete not used tags, delete duplicates.

  :param api:
  :param existing_monitors: monitors found in kuma
  :param delete: if true delete tags from kuma
  :return:
  """

  config_tags = []
  for c in config_monitors:
    if "tags" in c.keys():
      config_tags.extend(c['tags'])
  # unique list
  config_tags = list(set(config_tags))

  existing_tags, existing_tags_id = get_tags(api)
  logger.debug(f'existing_monitors tags: {existing_tags}')
  existing_tag_names = [t['name'] for t in existing_tags]
  to_add = set(config_tags) - set(existing_tag_names)
  to_delete = set(existing_tag_names) - set(config_tags)
  logger.debug(f'tags to_add: {to_add}, to_delete: {to_delete}')
  logger.info(f'tags to_add: {len(to_add)}, to_delete: {len(to_delete)}')

  # remove duplicate tags
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
  new_tags_id = {t['name']: t for t in existing_tags}

  return new_tags_id, existing_tags


def replace_tag_names_with_id(config_tags: list[str], existing_tags: Dict[str, Any]) -> list[int]:
  tags_id = []
  for ctag in config_tags:
    for d in existing_tags:
      if d['name'] == ctag:
        tags_id.append(d['id'])

  tags_id2 = [d['id'] for ctag in config_tags for d in existing_tags if d['name'] == ctag]
  logger.debug(f'tags_id2: {tags_id2}, tags_id: {tags_id}')
  return tags_id


def convert_time_range(thismaintenance) -> Dict[str, Any]:
  if 'timeRange' not in thismaintenance.keys():
    return thismaintenance

  new_time_range = []
  for elt in thismaintenance["timeRange"]:
    splitted = elt.split(':')
    new_time_range.append({"hours": int(splitted[0]), "minutes": int(splitted[1]), "seconds": int(splitted[2])})
  thismaintenance['timeRange'] = new_time_range

  return thismaintenance


def process_maintenance(api: UptimeKumaApi = None, existing_maintenance: Dict[str, Any] = None,
                        config_maintenance: list[str] = None,
                        existing_monitors: Dict[str, Any] = None,
                        delete: bool = False) -> dict[LiteralString | str, str | Any]:
  """
  add/edit/delete maintenance
  update monitors attached to a maintenance
  :param api:
  :param existing_maintenance:
  :param config_maintenance:
  :param existing_monitors:
  :param delete:
  :return:
  """
  config_maintenance_dict = {t['title']: t for t in config_maintenance}
  config_maintenance_names = [t['title'] for t in config_maintenance]
  existing_maintenance_dict = {t['title']: t for t in existing_maintenance}
  existing_maintenance_names = [t['title'] for t in existing_maintenance]

  # remove duplicate existing maintenance
  c = Counter(existing_maintenance_names)
  logger.debug(f'maintenance counter: {c}')
  duplicates = {k: v for k, v in c.items() if v > 1}
  logger.info(f'duplicate maintenance found: {len(duplicates)}')
  logger.debug(f'duplicate maintenance found: {len(duplicates)}, {duplicates}')

  to_add = set(config_maintenance_names) - set(existing_maintenance_names)
  to_delete = set(existing_maintenance_names) - set(config_maintenance_names)
  to_edit = set(config_maintenance_names) & set(existing_maintenance_names)

  added = []
  deleted = []
  edited = []

  monitors = api.get_monitors()

  # if required, maintenance is deleted
  if delete and len(to_delete) > 0:
    for elt in to_delete:
      id = [v['id'] for k, v in existing_maintenance_dict.items() if k == elt][0]
      result = api.delete_maintenance(id_=id)
      logger.info(f"Deleting removed maintenance '{elt}', id={id}, result: {result['msg']}")
      logger.debug(f"Deleting removed maintenance '{elt}', id={id}, result: {result}")
      deleted.append(elt)
      existing_maintenance_dict.pop(elt)

  # add existing maintenance
  for elt in to_add:
    thismaintenance = [m for m in config_maintenance if m['title'] == elt][0]
    thismaintenance = convert_time_range(thismaintenance)
    # extract monitor list id
    if 'monitorslist' in thismaintenance:
      monitors_list = thismaintenance.pop('monitorslist', None)
      if str(monitors_list[0]).lower() == 'all':
        monitors_id_list = [l['id'] for l in monitors]
      else:
        monitors_id_list = [l['id'] for l in monitors if l['name'] in monitors_list]
    else:
      monitors_id_list = []
    # add maintenance
    result = api.add_maintenance(**thismaintenance)
    id = result['maintenanceID']
    logger.info(f"Adding maintenance '{elt}', id={id}, result: {result['msg']}")
    logger.debug(f"Adding maintenance '{elt}', id={id}, result: {result}")
    existing_maintenance_dict[elt] = result
    added.append(elt)
    # update monitors association
    monitors_id = []
    for l in monitors_id_list:
      monitors_id.append({'id': l})
    result = api.add_monitor_maintenance(id_=id, monitors=monitors_id)
    logger.info(f"Adding {len(monitors_id)} monitors to maintenance '{elt}', id={id}, result: {result['msg']}")
    logger.debug(f"Adding monitors {monitors_id} to maintenance '{elt}', id={id}, result: {result}")

  # edit existing maintenance
  for elt in to_edit:
    id = existing_maintenance_dict[elt]['id']
    thismaintenance = [m for m in config_maintenance if m['title'] == elt][0]
    thismaintenance = convert_time_range(thismaintenance)
    # extract monitor list id
    if 'monitorslist' in thismaintenance:
      monitors_list = thismaintenance.pop('monitorslist', None)
      if str(monitors_list[0]).lower() == 'all':
        monitors_id_list = [l['id'] for l in monitors]
      else:
        monitors_id_list = [l['id'] for l in monitors if l['name'] in monitors_list]
    else:
      monitors_id_list = []
    # edit maintenance
    result = api.edit_maintenance(id, **thismaintenance)
    logger.info(f"Editing maintenance '{elt}', id={id}, result: {result['msg']}")
    logger.debug(
      f'Editing maintenance "{elt}", id={str(id) + "/" + str(result["maintenanceID"])}, result: {result}')
    edited.append(elt)
    # update monitors association
    # TODO delete if existing ?
    # current_monitors= api.get_monitor_maintenance(id_=id)
    # current_monitors_id = [ c['id'] for c in current_monitors ]
    # to_delete = monitors_id_list - current_monitors_id
    # result = api.
    monitors_id = []
    for l in monitors_id_list:
      monitors_id.append({'id': l})
    result = api.add_monitor_maintenance(id_=id, monitors=monitors_id)
    logger.info(f"Adding {len(monitors_id)} monitors to maintenance '{elt}', id={id}, result: {result['msg']}")
    logger.debug(f"Adding monitors {monitors_id} to maintenance '{elt}', id={id}, result: {result}")

  logger.info(f'added: {len(added)}, deleted: {len(deleted)}, edited: {len(edited)}')
  logger.debug(f'added: {added}, deleted: {deleted}, edited: {edited}')

  return existing_maintenance_dict


def processed_monitors_paused(api: 'UptimeKumaApi', monitors_paused: list[str], dry_run: bool = True):
  if len(monitors_paused) == 0:
    return
  try:
    kuma_monitors = api.get_monitors()
  except Exception as e:
    logger.exception(f'Cannot get monitors: {e}')

  monitor_paused_id = [(k.get('id'), k.get('name')) for k in kuma_monitors if k.get('name') in monitors_paused]
  for id, name in monitor_paused_id:
    try:
      result = api.pause_monitor(id)
      logger.info(f'Monitor {name} ({id}): {result['msg']}')
    except Exception as e:
      logger.error(f'pause_monitor {id}, {name}: {e}')


def import_config_into_kuma(file_path: str, api: 'UptimeKumaApi' = None, dry_run: bool = False,
                            delete: bool = False) -> None:
  """
  import toml config into uptimekuma
  :param file_path: toml config file path
  :param api: UptimeKumaApi
  :param dry_run: if true do not import
  :param delete: if true, delete monitors not present in toml files
  """
  e, config_docker_hosts, config_monitors, config_notifications, config_maintenance, config_status_pages = load_toml_config_file(
    file_path)
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

  new_statuses_pages = process_status_pages(api=api, config_status_pages=config_status_pages, delete=delete)

  # add/remove tags
  new_tags_id, new_tags = add_remove_tags(api=api, config_monitors=config_monitors, delete=delete)

  # add/remove/edit Notifications
  existing_notifications = api.get_notifications()
  new_notifications = process_notifications(api=api, existing_notifications=existing_notifications,
                                            config_notifications=config_notifications, delete=delete)

  # add/remove Groups
  config_groups = set([g['group'] for g in config_monitors if 'group' in g.keys()])
  new_groups = process_groups(api=api, existing_groups=existing_groups, config_groups=config_groups, delete=delete)

  # récupérer et synchroniser les docker hosts
  existing_docker_hosts = api.get_docker_hosts()
  new_docker_hosts = process_docker_hosts(api=api, config_docker_hosts=config_docker_hosts,
                                          existing_docker_hosts=existing_docker_hosts, delete=delete)

  # construire index name -> id pour lookup O(1)
  name_to_id = {dh['name']: dh['id'] for dh in new_docker_hosts}

  # remplacer docker_host (si string) par son id, en validant l'existence
  for c in config_monitors:
    name = c.get("docker_host")
    if isinstance(name, str):
      docker_id = name_to_id.get(name)
      if docker_id is None:
        raise ConfigError(f"Docker host named '{name}' not found")
      c['docker_host'] = docker_id

  # add/edit/delete containers
  # TODO

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
      deleted.append(elt)

  # Monitors
  monitor_processed = []
  monitors_paused = []
  for m in config_monitors:

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

    # save paused monitor for later use
    if 'active' in payload.keys():
      if payload['active'] == False:
        logger.debug(f'Adding {name} to paused monitors ({monitors_paused})')
        monitors_paused.append(payload['name'])
      payload.pop('active', None)

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
      # replace_tag_names_with_id(payload['tags'], existing_tags))
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

    if kuma_monitor is not None and kuma_monitor.get('name') not in monitors_paused:
      try:
        result = api.resume_monitor(mon_id)
        logger.debug(f'resume monitor {name}: {result}')
      except Exception as e:
        logger.exception(f'resume monitor: {payload["name"]}, error: {e}')

    logger.info(f"Import completed for '{name}'.")

    # All monitors are processed

    # handle tags
    # restore tags from config
    m['tags'] = payload_tags
    update_monitor_tags(api=api, monitor_id=mon_id, monitor=m, kuma_monitor=kuma_monitor, existing_tags=new_tags_id,
                        delete=delete)
  logger.debug(f'result: {result}, id_tags: {id_tags}')

  # handle paused monitor
  result = processed_monitors_paused(api=api, monitors_paused=monitors_paused, dry_run=dry_run)

  # resume all paused groups
  for g in new_groups:
    try:
      result = api.resume_monitor(new_groups[g].get('id'))
    except Exception as e:
      logger.exception(f'Cannot resume group {new_groups[g].get('name')}: ${result}')

  # add/edit/delete maintenance: has to after all monitors add/edit/delete
  existing_maintenance = api.get_maintenances()
  new_maintenance = process_maintenance(api=api, existing_maintenance=existing_maintenance,
                                        config_maintenance=config_maintenance,
                                        existing_monitors=existing_monitors, delete=delete)


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
        try:
          result = api.delete_monitor_tag(tag_id=d, monitor_id=monitor_id)
          logger.info(f"Deleting tag '{d}' to monitor {monitor_id}, result: {result['msg']}")
          logger.debug(f"Deleting tag '{d}' to monitor {monitor_id}, result: {result}")
        except Exception as e:
          logger.exception(f'Error deleting tag {d} to monitor {monitor_id}, result: {e}')

  #
  for tag in add_tags:
    if tag not in [k['tag_id'] for k in kuma_monitor['tags']]:
      try:
        result = api.add_monitor_tag(tag_id=tag, monitor_id=monitor_id)
        logger.info(f"Adding tag '{tag}' to monitor {monitor_id}, result: {result['msg']}")
        logger.debug(f"Adding tag '{tag}' to monitor {monitor_id}, result: {result}")
      except Exception as e:
        logger.error(f'error adding tag {tag} to monitor {monitor_id}: {e}')


# ----------------------------------------------------------
# TODO: tested

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
  Exception, list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
  e = None
  monitors = []
  notifications = []
  docker = []
  maintenances = []

  if not Path(file_path).is_file():
    logger.error(f"File path '{file_path}' not found.")
  try:
    docker, monitors, notifications, maintenances, statuses = load_toml(file_path)
  except (ConfigError, Exception) as e:
    logger.error(f"Configuration error: {e}")
    sys.exit(1)
  return e, docker, monitors, notifications, maintenances, statuses


def main():
  # set logger
  format = '%(asctime)s - %(levelname)s - %(name)s [%(funcName)s][%(lineno)d] - %(message)s'
  logging.basicConfig(format=format, level=logging.INFO)
  logger = logging.getLogger(__name__)
  logger.setLevel(logging.INFO)

  p = argparse.ArgumentParser(description="Import monitors from TOML into UptimeKuma via UptimeKumaApi")
  p.add_argument("--file", "-f", help="TOML file path", default="kuma.toml")
  p.add_argument("--api-url", "-a", help="UptimeKuma API URL or connection string", default="http://localhost:3001")
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
  try:
    api = UptimeKumaApi(url=args.api_url, ssl_verify=ssl_true, timeout=20)
  except Exception as e:
    logger.error(f'{args.api_url}: {e}')
    sys.exit(1)

  if args.token:
    token = args.token
  else:
    token = get_token_from_kuma_api(kuma_api=api, username=args.username, password=args.password)
  logger.debug(f'token: {token}')

  if token is None:
    logger.error(f'Error while operating with a token on api')
    sys.exit(1)

  result = api.get_database_size()
  logger.info(f'Database size: {result["size"]}')
  result = api.need_setup()
  logger.info(f'need setup: {result}')
  result = api.info()
  logger.info(f'info: {result}')
  # result = api.uptime()
  # logger.info(f'uptime: {result}')

  import_config_into_kuma(api=api, file_path=CDIR + os.sep + args.file, dry_run=args.dry_run, delete=args.delete)

  result = api.disconnect()
  logger.debug(f'result: {result}')


if __name__ == "__main__":
  main()
