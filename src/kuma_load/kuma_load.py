#!/usr/bin/env python3
import os
import random
import sys
import logging
import argparse
import importlib
from pathlib import Path
from typing import List, Dict, Any, Counter, LiteralString, Tuple, Optional

from dataclasses import dataclass, field
from typing import Optional

# =============================================================================
# try tomllib (Py3.11+), otherwise tomli
# =============================================================================
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
  print('Missing UptimeKumaApi, python3 -m pip install git+https://github.com/edgd1er/uptime-kuma-api.git@v2-support')


# =============================================================================
# exception classes
# =============================================================================

class KumaLoadError(Exception):
  """Base exception for kuma_load."""
  pass


class ConfigError(KumaLoadError):
  """configuration error."""
  pass


class APIError(KumaLoadError):
  """API error."""
  pass

class ConnectionError(APIError):
  """Error connecting to API."""
  pass

class DataFetchError(APIError):
  """Error fetching data."""
  pass

# =============================================================================
# global variables
# =============================================================================
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())
LDIR = os.path.dirname(os.path.realpath(__file__))
CDIR = os.getcwd()

REQUIRED_MONITOR_FIELDS = {"name", "type"}
VALID_MONITOR_TYPES = {
  "group", "http", "port", "ping", "keyword", "json_query", "grpc_keyword", "dns", "docker",
  "real_browser", "push", "steam", "gamedig", "mqtt", "kafka_producer", "sqlserver", "postgres",
  "mysql", "mongodb", "radius", "redis", "tailscale_ping"
}
VALID_AUTH_METHODS = {"none", "http_basic", "ntlm", "mtls", "oauth2_cc"}


# =============================================================================
# classes
# =============================================================================

@dataclass
class ImportConfig:
  """
  loaded configuration structure, from TOML file

  Has all configuration data, better organization, type enforced
  """
  monitors: List[Dict[str, Any]] = field(default_factory=list)
  notifications: List[Dict[str, Any]] = field(default_factory=list)
  docker_hosts: Optional[Dict[str, Any]] = field(default_factory=list)
  maintenances: List[Dict[str, Any]] = field(default_factory=list)
  status_pages: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ExistingState:
  """
  Existing state fetched from the UptimeKuma API.

  Organize entities with a name mapping for an access O(1).
  """
  monitors: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # name -> monitor
  groups: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # name -> group
  notifications: List[Dict[str, Any]] = field(default_factory=list)
  docker_hosts: List[Dict[str, Any]] = field(default_factory=list)
  maintenances: List[Dict[str, Any]] = field(default_factory=list)
  status_pages: List[Dict[str, Any]] = field(default_factory=list)
  tags: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # name -> tag


@dataclass
class ProcessedEntities:
  """
  Class for processed entities.

  Contient les nouvelles entités créées ou modifiées, avec leurs
  mappings name -> id pour la résolution des références.
  """
  status_pages: Any = None
  tags: List[Dict[str, Any]] = field(default_factory=list)
  tags_id: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # name -> tag dict
  notifications: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # name -> notification
  groups: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # name -> group
  docker_hosts: List[Dict[str, Any]] = field(default_factory=list)


# =============================================================================
# functions
# =============================================================================

def fix_api():
  # api L"incident": r2["incident"], - W  #"incident": r2["incidents"],
  # api LL2173: status_page.pop("maintenanceList"), add status_page.pop("autoRefreshInterval")
  # analyticsId
  # data.pop('analyticsId')

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
    logger.error("Authentication error")
    try:
      kuma_api.disconnect()
    except Exception:
      logger.error("kuma_api.disconnect() failed", exc_info=False)
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


# =============================================================================
# FONCTION 1 : load config from file
# =============================================================================
def load_toml(path: str) -> ImportConfig:
  try:
    with open(path, "rb") as f:
      data = tomllib.load(f)
  except FileNotFoundError:
    raise ConfigError(f"TOML file not found: {path}")
  except tomllib.TOMLDecodeError as e:
    raise ConfigError(f"Invalid TOML: {e}") from e

  docker: Optional[Dict[str, Any]] = []
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

  # if empty config
  if len(monitors) == 0 and len(notifications) == 0:
    logger.error(
      f"Empty monitors config ({len(monitors)}) or empty config_notifications ({len(notifications)})")
    raise ConfigError(
      "Configuration must contain at least one monitor or notification"
    )

  return ImportConfig(docker_hosts=docker, monitors=monitors, maintenances=maintenances, status_pages=statuses,
                      notifications=notifications)


# =============================================================================
# FUNCTION 2 : fetch_existing_state
# =============================================================================

def fetch_existing_state(api: Optional['UptimeKumaApi']) -> ExistingState:
  """
  Récupère l'état existant depuis l'API UptimeKuma.

  Cette fonction centralise tous les appels API pour récupérer l'état
  actuel de l'instance UptimeKuma.

  Args:
      api: Instance de UptimeKumaApi (peut être None)

  Lève:
      ValueError: Si api est None
      APIError: En cas d'erreur lors de la récupération

  Retourne:
      ExistingState: Structure contenant toutes les entités existantes
  """
  if api is None:
    raise ValueError("API must not be None")

  try:
    # Récupérer les moniteurs existants
    existing_config, existing_monitors = get_monitors(api)

    # Extraire les groupes (qui sont des moniteurs avec type='group')
    existing_groups = {
      g['name']: g for g in existing_config if g.get('type') == 'group'
    }

    # Récupérer les tags
    existing_tags, _ = get_tags(api)
    existing_tags_dict = {t['name']: t for t in existing_tags}

    return ExistingState(
      monitors=existing_monitors,
      groups=existing_groups,
      notifications=api.get_notifications(),
      docker_hosts=api.get_docker_hosts(),
      maintenances=api.get_maintenances(),
      status_pages=api.get_status_pages(),
      tags=existing_tags_dict,
    )

  except Exception as e:
    raise APIError(f"Failed to fetch existing state: {e}") from e


# =============================================================================
# FONCTION 3 : process_independent_entities
# =============================================================================

def process_independent_entities(
        api: 'UptimeKumaApi',
        config: ImportConfig,
        existing: ExistingState,
        delete: bool
) -> ProcessedEntities:
  """
  process entities that have not links between them.
  status_pages, tags, notifications, groups, docker

  No order is required.

  :argument api: UptimeKumaApi instance
  :argument config: loaded configuration
  :argument existing: existing state
  :argument delete: if True, delete entities not found in toml file.

  :returns
      ProcessedEntities: Entités traitées avec leurs mappings
  """

  # Traiter les status pages
  new_status_pages = process_status_pages(
    api=api,
    config_status_pages=config.status_pages,
    delete=delete
  )

  # Traiter les tags
  new_tags_id, new_tags = add_remove_tags(
    api=api,
    config_monitors=config.monitors,
    delete=delete
  )

  # Traiter les notifications
  new_notifications = process_notifications(
    api=api,
    existing_notifications=existing.notifications,
    config_notifications=config.notifications,
    delete=delete
  )

  # Extraire les noms des groupes de la config des moniteurs
  config_groups = {m['group'] for m in config.monitors if 'group' in m}

  # Traiter les groupes
  new_groups = process_groups(
    api=api,
    existing_groups=existing.groups,
    config_groups=config_groups,
    delete=delete
  )

  # Traiter les docker hosts
  new_docker_hosts = process_docker_hosts(
    api=api,
    config_docker_hosts=config.docker_hosts,
    existing_docker_hosts=existing.docker_hosts,
    delete=delete
  )

  return ProcessedEntities(
    status_pages=new_status_pages,
    tags=new_tags,
    tags_id=new_tags_id,
    notifications=new_notifications,
    groups=new_groups,
    docker_hosts=new_docker_hosts,
  )


# =============================================================================
# FONCTION 4 : resolve_all_references
# =============================================================================

def resolve_all_references(config: ImportConfig, processed: ProcessedEntities) -> None:
  """

  Resolve references by names to ids in imported config.

  This function parses all imported config monitors and replace references by names (groupes, docker hosts, notifications)
  by their corresponding IDs.

  Change in place config.monitors.

  :argument config: Configuration chargée
  /:argument processed: Entités déjà traitées (contient les mappings name->id)

  Lève:
      ConfigError: Si une référence n'est pas trouvée
  """
  # Créer les mappings name -> id pour un accès rapide
  docker_name_to_id = {dh['name']: dh['id'] for dh in processed.docker_hosts}
  notification_name_to_id = {n['name']: n['id'] for n in processed.notifications.values()}
  group_name_to_id = {name: g['id'] for name, g in processed.groups.items()}

  # CORRECTION BUG #4 : Ne pas modifier la liste pendant itération
  # Parcourir chaque moniteur et résoudre ses références
  for monitor in config.monitors:

    # Résoudre docker_host (si c'est une string, la remplacer par l'ID)
    if 'docker_host' in monitor and isinstance(monitor['docker_host'], str):
      docker_name = monitor['docker_host']
      if docker_name not in docker_name_to_id:
        raise ConfigError(f"Docker host '{docker_name}' not found in existing docker hosts")
      monitor['docker_host'] = docker_name_to_id[docker_name]

    # Résoudre notificationIDList (si contient des noms, les remplacer par des IDs)
    if 'notificationIDList' in monitor:
      resolved_ids = []
      for notif in monitor['notificationIDList']:
        if isinstance(notif, str):
          # C'est un nom de notification
          if notif not in notification_name_to_id:
            raise ConfigError(f"Notification '{notif}' not found in existing notifications")
          resolved_ids.append(notification_name_to_id[notif])
        else:
          # C'est déjà un ID
          resolved_ids.append(notif)
      monitor['notificationIDList'] = resolved_ids

    # Résoudre le groupe (convertir en parent ID)
    if 'group' in monitor:
      group_name = monitor['group']
      if group_name not in group_name_to_id:
        raise ConfigError(f"Group '{group_name}' not found in existing groups")
      monitor['parent'] = group_name_to_id[group_name]
      # CORRECTION BUG #6 : Supprimer la clé 'group' après résolution
      monitor.pop('group', None)


# =============================================================================
# FONCTIONS AUXILIAIRES POUR LES MONITEURS
# =============================================================================

def find_duplicate_monitors(monitor_names: List[str]) -> List[str]:
  """
  Trouve les noms de moniteurs dupliqués.

  Args:
      monitor_names: Liste des noms de moniteurs

  Retourne:
      Liste des noms qui apparaissent plus d'une fois
  """
  c = Counter(monitor_names)
  return [name for name, count in c.items() if count > 1]


# =============================================================================
# FONCTION 5 : delete_monitors
# =============================================================================

def delete_monitors(
        api: 'UptimeKumaApi',
        existing_monitors: Dict[str, Dict[str, Any]],
        monitors_to_delete: set
) -> List[str]:
  """
  Supprime les moniteurs non présents dans la configuration.

  Args:
      api: Instance de UptimeKumaApi
      existing_monitors: Moniteurs existants (name -> monitor dict)
      monitors_to_delete: Ensemble des noms de moniteurs à supprimer

  Retourne:
      Liste des noms de moniteurs supprimés
  """
  deleted = []

  for monitor_name in monitors_to_delete:
    # CORRECTION BUG #5 : Vérifier que le moniteur existe avant d'accéder à [0]
    if monitor_name not in existing_monitors:
      logger.warning(f"Monitor '{monitor_name}' not found in existing monitors, skipping deletion")
      continue

    monitor_info = existing_monitors[monitor_name]
    monitor_id = monitor_info['id']

    try:
      result = api.delete_monitor(id_=monitor_id)
      logger.info(f"Deleting removed monitor '{monitor_name}', id={monitor_id}, result: {result.get('msg', '')}")
      logger.debug(f"Deleting removed monitor '{monitor_name}', id={monitor_id}, result: {result}")
      deleted.append(monitor_name)
    except Exception as e:
      logger.error(f"Error deleting monitor '{monitor_name}': {e}")

  return deleted


# =============================================================================
# FONCTION 6 : update_existing_monitor
# =============================================================================

def update_existing_monitor(
        api: 'UptimeKumaApi',
        existing_monitor: Dict[str, Any],
        payload: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
  """
  Met à jour un moniteur existant.

  Args:
      api: Instance de UptimeKumaApi
      existing_monitor: Moniteur existant (avec id, name, etc.)
      payload: Données à mettre à jour

  Retourne:
      Dict avec les infos du moniteur mis à jour, ou None en cas d'erreur
  """
  mon_id = existing_monitor['id']
  monitor_name = existing_monitor['name']

  try:
    result = api.edit_monitor(mon_id, **payload)
    logger.info(f"Updating monitor '{monitor_name}', id={mon_id}, result: {result.get('msg', '')}")
    logger.debug(f"Updating monitor '{monitor_name}', id={mon_id}, result: {result}, payload: {payload}")

    # Récupérer les infos complètes du moniteur
    kuma_monitor = api.get_monitor(id_=result.get('monitorID', mon_id))
    return kuma_monitor

  except Exception as e:
    logger.error(f"Error updating monitor '{monitor_name}': {e}")
    logger.debug(f"Error updating monitor '{monitor_name}', payload: {payload}, exception: {e}")
    return None


# =============================================================================
# FONCTION 7 : create_new_monitor
# =============================================================================

def create_new_monitor(
        api: 'UptimeKumaApi',
        payload: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
  """
  Crée un nouveau moniteur.

  Args:
      api: Instance de UptimeKumaApi
      payload: Données du moniteur à créer

  Retourne:
      Dict avec les infos du moniteur créé, ou None en cas d'erreur
  """
  monitor_name = payload.get('name', 'unknown')

  try:
    result = api.add_monitor(**payload)
    logger.info(
      f"Creating monitor '{monitor_name}', id={result.get('monitorID', 'unknown')}, result: {result.get('msg', '')}")
    logger.debug(f"Creating monitor '{monitor_name}', result: {result}, payload: {payload}")

    # Récupérer les infos complètes du moniteur
    kuma_monitor = api.get_monitor(id_=result.get('monitorID'))
    return kuma_monitor

  except Exception as e:
    logger.error(f"Error creating monitor '{monitor_name}': {e}")
    logger.debug(f"Error creating monitor '{monitor_name}', payload: {payload}, exception: {e}")
    return None


# =============================================================================
# FONCTION 8 : resume_monitor_if_needed
# =============================================================================

def resume_monitor_if_needed(
        api: 'UptimeKumaApi',
        kuma_monitor: Dict[str, Any],
        is_paused: bool,
        monitors_paused: List[str]
) -> None:
  """
  Reprend un moniteur s'il n'est pas dans la liste des paused.

  Args:
      api: Instance de UptimeKumaApi
      kuma_monitor: Moniteur Kuma (avec id, name, etc.)
      is_paused: Si True, le moniteur doit être paused
      monitors_paused: Liste des noms de moniteurs à pauser
  """
  if kuma_monitor is None:
    return

  monitor_name = kuma_monitor.get('name', '')
  monitor_id = kuma_monitor['id']

  # CORRECTION BUG #7 : Utiliser '' comme valeur par défaut au lieu de []
  # et vérifier que mon_id est défini
  if is_paused:
    # Ce moniteur doit être paused, il sera traité plus tard
    monitors_paused.append(monitor_name)
  elif monitor_name not in monitors_paused:
    # Ce moniteur n'est pas paused, le reprendre
    try:
      result = api.resume_monitor(monitor_id)
      logger.debug(f'Resumed monitor {monitor_name}: {result}')
    except Exception as e:
      logger.exception(f'Error resuming monitor {monitor_name}: {e}')


# =============================================================================
# FONCTION 9 : update_monitor_tags
# =============================================================================

def update_monitor_tags_for_config(
        api: 'UptimeKumaApi',
        kuma_monitor: Dict[str, Any],
        config_tags: List[str],
        new_tags_id: Dict[str, Dict[str, Any]],
        delete: bool = False
) -> None:
  """
  Met à jour les tags d'un moniteur selon la configuration.

  Args:
      api: Instance de UptimeKumaApi
      kuma_monitor: Moniteur Kuma (avec id, name, tags, etc.)
      config_tags: Liste des noms de tags de la configuration
      new_tags_id: Mapping name -> tag dict
      delete: Si True, supprime les tags non présents
  """
  if not config_tags:
    return

  monitor_id = kuma_monitor['id']

  # CORRECTION BUG #3 : Utiliser .get() pour accéder à 'tags'
  existing_tags = kuma_monitor.get('tags', [])
  existing_tag_ids = {t.get('tag_id') for t in existing_tags if 'tag_id' in t}

  # Résoudre les noms de tags en IDs
  tag_ids = []
  for tag_name in config_tags:
    if tag_name in new_tags_id:
      tag_ids.append(new_tags_id[tag_name]['id'])

  # Ajouter les nouveaux tags
  for tag_id in tag_ids:
    if tag_id not in existing_tag_ids:
      try:
        api.add_monitor_tag(tag_id=tag_id, monitor_id=monitor_id)
        logger.info(f"Added tag {tag_id} to monitor {monitor_id}")
      except Exception as e:
        logger.error(f"Error adding tag {tag_id} to monitor {monitor_id}: {e}")

  # TODO: Implémenter la suppression des tags si delete=True


# =============================================================================
# FONCTION 10 : process_single_monitor
# =============================================================================

def process_single_monitor(
        api: 'UptimeKumaApi',
        monitor_config: Dict[str, Any],
        existing_monitors: Dict[str, Dict[str, Any]],
        new_groups: Dict[str, Dict[str, Any]],
        new_tags_id: Dict[str, Dict[str, Any]],
        dry_run: bool,
        monitors_paused: List[str],
        monitor_processed: List[str]
) -> Optional[Dict[str, Any]]:
  """
  Traite un seul moniteur de la configuration.

  Cette fonction gère :
  - La normalisation du moniteur
  - La gestion des groupes
  - La gestion de l'état paused
  - La création ou la mise à jour
  - L'application des tags

  Args:
      api: Instance de UptimeKumaApi
      monitor_config: Configuration du moniteur (dict)
      existing_monitors: Moniteurs existants (name -> monitor dict)
      new_groups: Groupes traités (name -> group dict)
      new_tags_id: Tags traités (name -> tag dict)
      dry_run: Si True, n'applique pas les changements
      monitors_paused: Liste des moniteurs à pauser (modifiée en place)
      monitor_processed: Liste des moniteurs traités (modifiée en place)

  Retourne:
      kuma_monitor: Moniteur Kuma créé/mis à jour, ou None en cas d'erreur
  """

  name = monitor_config['name']

  # CORRECTION BUG #6 : Initialiser mon_id à None
  mon_id = None
  kuma_monitor = None

  # Normaliser le moniteur
  payload = normalize_monitor_for_api(monitor_config)

  # Gérer le groupe
  if 'group' in monitor_config:
    payload['parent'] = new_groups[monitor_config['group']]['id']
    payload.pop('group', None)

  # Gérer l'état paused
  is_paused = monitor_config.get('active') is False
  if 'active' in payload:
    payload.pop('active', None)

  # Gestion des tags
  config_tags = payload.pop('tags', [])

  # Mode dry-run
  if dry_run:
    if name in existing_monitors:
      logger.info(
        f"[DRY-RUN] Would update monitor '{name}' "
        f"(id={existing_monitors[name]['id']}) with payload: {payload}"
      )
    else:
      logger.info(f"[DRY-RUN] Would create monitor '{name}' with payload: {payload}")
    return None

  # Créer ou mettre à jour le moniteur
  if name in existing_monitors:
    kuma_monitor = update_existing_monitor(api, existing_monitors[name], payload)
    if kuma_monitor:
      mon_id = kuma_monitor['id']
      monitor_processed.append(name)
  else:
    kuma_monitor = create_new_monitor(api, payload)
    if kuma_monitor:
      mon_id = kuma_monitor['id']
      monitor_processed.append(name)

  # Reprendre le moniteur s'il n'est pas paused
  if kuma_monitor:
    resume_monitor_if_needed(api, kuma_monitor, is_paused, monitors_paused)

    # Appliquer les tags
    update_monitor_tags_for_config(api, kuma_monitor, config_tags, new_tags_id)

  return kuma_monitor


# =============================================================================
# FONCTION 11 : process_all_monitors
# =============================================================================

def process_all_monitors(
        api: 'UptimeKumaApi',
        config: ImportConfig,
        existing: ExistingState,
        processed: ProcessedEntities,
        delete: bool,
        dry_run: bool
) -> Tuple[List[str], List[str]]:
  """
  Traite tous les moniteurs de la configuration.

  Cette fonction orchestre :
  - L'identification des changements (à ajouter, supprimer, modifier)
  - La suppression des moniteurs non présents
  - Le traitement de chaque moniteur

  Args:
      api: Instance de UptimeKumaApi
      config: Configuration chargée
      existing: État existant
      processed: Entités déjà traitées
      delete: Si True, supprime les moniteurs non présents
      dry_run: Si True, n'applique pas les changements

  Retourne:
      Tuple de (monitors_paused, monitor_processed)
  """
  existing_monitors = existing.monitors

  # Identifier les changements
  # CORRECTION : Filtrer les groupes pour ne garder que les moniteurs
  existing_monitor_names = [
    name for name, mon in existing_monitors.items()
    if mon.get('type') != 'group'
  ]
  config_monitor_names = [m['name'] for m in config.monitors]

  to_delete = set(existing_monitor_names) - set(config_monitor_names)
  to_add = set(config_monitor_names) - set(existing_monitor_names)
  to_edit = set(config_monitor_names) & set(existing_monitor_names)

  # Détecter les doublons
  duplicates = find_duplicate_monitors(existing_monitor_names)
  if duplicates:
    logger.info(f"Duplicate monitors found: {duplicates}")

  # Supprimer les moniteurs non présents dans la config
  monitors_paused: List[str] = []
  monitor_processed: List[str] = []

  if delete and to_delete:
    deleted = delete_monitors(api, existing_monitors, to_delete)
    logger.info(f"Deleted {len(deleted)} monitors: {deleted}")

  # Traiter chaque moniteur de la config
  for monitor_config in config.monitors:
    process_single_monitor(
      api=api,
      monitor_config=monitor_config,
      existing_monitors=existing_monitors,
      new_groups=processed.groups,
      new_tags_id=processed.tags_id,
      dry_run=dry_run,
      monitors_paused=monitors_paused,
      monitor_processed=monitor_processed,
    )

  logger.info(
    f"Monitors processed: {len(monitor_processed)}, "
    f"Paused: {len(monitors_paused)}, "
    f"Added: {len(to_add)}, Edited: {len(to_edit)}, Deleted: {len(to_delete if delete else set())}"
  )

  return monitors_paused, monitor_processed


# =============================================================================
# FONCTION 12 : resume_paused_groups
# =============================================================================

def resume_paused_groups(
        api: 'UptimeKumaApi',
        new_groups: Dict[str, Dict[str, Any]]
) -> None:
  """
  Reprend tous les groupes qui ont été créés.

  Les groupes sont créés paused par défaut dans Uptime Kuma,
  donc on les reprend après leur création.

  Args:
      api: Instance de UptimeKumaApi
      new_groups: Groupes créés (name -> group dict)
  """
  for group_name, group_info in new_groups.items():
    try:
      group_id = group_info.get('id')
      if group_id:
        result = api.resume_monitor(group_id)
        logger.info(f"Resumed group '{group_name}' (id={group_id}), result: {result.get('msg', '')}")
    except Exception as e:
      logger.exception(f"Cannot resume group '{group_name}': {e}")


# =============================================================================
# FONCTION 13 : finalize_import
# =============================================================================

def finalize_import(
        api: 'UptimeKumaApi',
        config: ImportConfig,
        existing: ExistingState,
        processed: ProcessedEntities,
        monitors_paused: List[str],
        dry_run: bool,
        delete: bool
) -> None:
  """
  Finalize import with post-treatment.

  :arg api: Instance de UptimeKumaApi
  :arg existing: existinf state
  :arg processed: entities provessed!
  :arg monitors_paused: List of monitors to pause
  :arg dry_run: Si True, n'applique pas les changements
  :arg delete: if True, delete monitors not in config
  """

  # Reprendre tous les groupes paused
  resume_paused_groups(api, processed.groups)

  # Traiter les moniteurs paused
  if monitors_paused:
    processed_monitors_paused(api=api, monitors_paused=monitors_paused, dry_run=dry_run)

  # Traiter les maintenances (doit être après les moniteurs et groupes)
  existing_maintenance = existing.maintenances
  config_maintenance = config.maintenances

  # CORRECTION : Passer les bonnes références
  new_maintenance = process_maintenance(
    api=api,
    existing_maintenance=existing_maintenance,
    config_maintenance=config_maintenance,
    existing_groups=existing.groups,
    existing_monitors=existing.monitors,
    delete=delete
  )

  logger.info(f"Maintenance processed: {len(new_maintenance)} items")


# =============================================================================
# FUNCTION : normalize_monitor_for_api
# =============================================================================
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


# =============================================================================
# FUNCTION : process_notifications
# =============================================================================
def process_notifications(api: "UptimeKumaApi" = None, existing_notifications: list[Dict[str, Any]] = None,
                          config_notifications: list[Dict[str, Any]] = None, delete: bool = False) -> dict[
  Any, dict[str, Any] | Any]:

  if api is None:
    raise ValueError("api must not be None")

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
  return existing_notifications_dict


# =============================================================================
# FUNCTION : process_groups
# =============================================================================
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

  if api is None:
    raise ValueError(f'api must not be None')

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


# =============================================================================
# FUNCTION : process_docker_hosts
# =============================================================================
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


# =============================================================================
# FUNCTION : process_status_pages
# =============================================================================
def process_status_pages(api: 'UptimeKumaApi' = None, config_status_pages: Dict[str, Any] = {},
                         delete: bool = False) -> List[Dict[str, Any]]:
  if api is None:
    raise ValueError("api must not be None")

  config = [] if config_status_pages is None else config_status_pages
  processed_status_pages=[]

  existing_status_pages = []
  try:
    existing_status_pages = api.get_status_pages()
  except Exception as e:
    logger.error(f'get_status_pages: {e}')

  if len(existing_status_pages) == 0 and len(config) == 0:
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
      logger.error(f'Error deleting status page {slug}')
      logger.debug(f'Error deleting status page {slug}: {e}')

  for a in to_add:
    try:
      ret = api.add_status_page(slug=config_by_names[a]['slug'], title=config_by_names[a].get('title'))
      logger.info(f"Added status page {config_by_names[a]['slug']}: {ret['msg']}")
      logger.debug(f"Added status page {config_by_names[a]['slug']}: {ret}")
      ret = api.save_status_page(slug=config_by_names[a]['slug'], **config_by_names[a])
      if ret['msg'] == "Added":
        processed_status_pages.append(config_by_names[a])

    except Exception as e:
      logger.error(f'Error adding status page {config_by_names[a]["title"]}')
      logger.debug(f'Error adding status page {config_by_names[a]["title"]}: {e}')

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
      if type(ret) == list:
        processed_status_pages.append(edited)
    except Exception as e:
      logger.error(f'Error adding status page {edited["title"]}({edited["id"]})')
      logger.debug(f'Error adding status page {edited["title"]}({edited["id"]}: {e}')
      raise APIError(f'Error adding status page {edited["title"]}({edited["id"]}')

  for s in existing_status_pages:
    logger.info(f's: {s}')

  return processed_status_pages

# =============================================================================
# FUNCTION : add_remove_tags
# =============================================================================
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


# =============================================================================
# FUNCTION : update_monitor_tags
# =============================================================================
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
  tags = kuma_monitor.get('tags', [])
  delete_tags = [t['tag_id'] for t in tags if 'tag_id' in t and t['tag_id'] not in existing_tags]
  # duplicate tags
  c = Counter([k['tag_id'] for k in tags])
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
    if tag not in [k['tag_id'] for k in tags]:
      try:
        result = api.add_monitor_tag(tag_id=tag, monitor_id=monitor_id)
        logger.info(f"Adding tag '{tag}' to monitor {monitor_id}, result: {result['msg']}")
        logger.debug(f"Adding tag '{tag}' to monitor {monitor_id}, result: {result}")
      except Exception as e:
        logger.error(f'error adding tag {tag} to monitor {monitor_id}: {e}')


# =============================================================================
# FUNCTION : replace_tag_names_with_id
# =============================================================================
def replace_tag_names_with_id(config_tags: list[str], existing_tags: Dict[str, Any]) -> list[int]:
  tags_id = []
  for ctag in config_tags:
    if ctag in existing_tags:
      tags_id.append(existing_tags[ctag]['id'])

  tags_id2 = [existing_tags[ctag]['id'] for ctag in config_tags if ctag in existing_tags.keys()]
  logger.debug(f'tags_id2: {tags_id2}, tags_id: {tags_id}')
  return tags_id


# =============================================================================
# FUNCTION : convert_time_range
# =============================================================================
def convert_time_range(thismaintenance) -> Dict[str, Any]:
  if 'timeRange' not in thismaintenance.keys():
    return thismaintenance

  new_time_range = []
  for elt in thismaintenance["timeRange"]:
    splitted = elt.split(':')
    new_time_range.append({"hours": int(splitted[0]), "minutes": int(splitted[1]), "seconds": int(splitted[2])})
  thismaintenance['timeRange'] = new_time_range

  if 'dateRange' not in thismaintenance:
    thismaintenance['dateRange']=["",""]

  return thismaintenance


# =============================================================================
# FUNCTION : process_maintenance
# =============================================================================
def process_maintenance(api: UptimeKumaApi = None, existing_maintenance: Dict[str, Any] = {},
                        config_maintenance: List[Dict[str, Any]] = [],
                        existing_groups: Dict[str, Any] = {},
                        existing_monitors: Dict[str, Any] = {},
                        delete: bool = False) -> Dict[str, Any]:
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

  # check parameters
  if api is None:
    raise ValueError("api must not be None")

  if existing_maintenance is None:
    existing_maintenance = []

  if config_maintenance is None:
    config_maintenance = []

  if existing_groups is None:
    existing_groups = {}

  if existing_monitors is None:
    existing_monitors = {}

  config_maintenance_dict = {t['title']: t for t in config_maintenance}
  config_maintenance_names = [t['title'] for t in config_maintenance]
  existing_maintenance_dict = {t['title']: t for t in existing_maintenance}
  existing_maintenance_names = [t['title'] for t in existing_maintenance]
  existing_groups_names = [v['name'] for k, v in existing_groups.items()]

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
  monitors_id_full_list = []
  monitors_id_list = []

  monitors = api.get_monitors()
  existing_monitors_names = [v['name'] for k, v in existing_monitors.items()]

  # add existing maintenance
  for elt in to_add:
    temp = [m for m in config_maintenance if m['title'] == elt]
    if len(temp) < 1:
      logger.warning(f'maintenance {elt} not found in config_maintenance')
      continue

    thismaintenance = convert_time_range(temp[0])

    # extract monitor list id
    if 'monitorslist' in thismaintenance:
      monitors_list = thismaintenance.pop('monitorslist', ['all'])
      excluded_names = thismaintenance.pop('excluded', [])
      # if parent is in excluded, exclude child
      excluded = [existing_groups[e]['id'] for e in excluded_names if e in existing_groups_names]
      # if current name is in excluded, exclude current
      excluded_child = [v['id'] for k, v in existing_monitors.items() if v['name'] in excluded_names]
      excluded.extend(excluded_child)

      monitors_id_list = filter_monitors_for_maintenance(monitors=monitors, monitors_list=monitors_list,
                                                         excluded=excluded, excluded_names=excluded_names,
                                                         existing_groups=existing_groups,
                                                         existing_monitors=existing_monitors)
    # add maintenance
    result = api.add_maintenance(**thismaintenance)
    id = result.get('maintenanceID')
    msg = result.get('msg')
    if id is None or msg != "Added":
      logger.error(f"Maintenance creation failed: {result}")
      continue
    logger.info(f"Adding maintenance '{elt}', id={id}, result: {result['msg']}")
    logger.debug(f"Adding maintenance '{elt}', id={id}, result: {result}")
    thismaintenance['id']=id
    existing_maintenance_dict[elt] = thismaintenance
    added.append(elt)

    # update monitors association
    for l in monitors_id_list:
      monitors_id_full_list.append({'id': l})
    result = api.add_monitor_maintenance(id_=id, monitors=monitors_id_full_list)
    logger.info(
      f"Adding {len(monitors_id_full_list)} monitors to maintenance '{elt}', id={id}, result: {result['msg']}")
    logger.debug(f"Adding monitors {monitors_id_full_list} to maintenance '{elt}', id={id}, result: {result}")

  # edit existing maintenance
  for elt in to_edit:
    id = existing_maintenance_dict[elt]['id']
    thismaintenance = [m for m in config_maintenance if m['title'] == elt][0]
    thismaintenance = convert_time_range(thismaintenance)

    # extract monitor list id
    if 'monitorslist' in thismaintenance:
      monitors_list = thismaintenance.pop('monitorslist', [])
      excluded_names = thismaintenance.pop('excluded', [])
      # if parent is in excluded, exclude child
      excluded = [existing_groups[e]['id'] for e in excluded_names if e in existing_groups_names]
      # if current name is in excluded, exclude current
      excluded_child = [v['id'] for k, v in existing_monitors.items() if v['name'] in excluded_names]
      excluded.extend(excluded_child)

      monitors_id_list = filter_monitors_for_maintenance(monitors=monitors, monitors_list=monitors_list,
                                                         excluded=excluded, excluded_names=excluded_names,
                                                         existing_groups=existing_groups,
                                                         existing_monitors=existing_monitors)

    # edit maintenance
    try:
      result = api.edit_maintenance(id=id, **thismaintenance)
      # Vérifier que maintenanceID existe dans le résultat
      if "maintenanceID" not in result:
        maintenance_name = thismaintenance.get("name", thismaintenance.get("title", "unknown"))
        raise ConfigError(
          f"Maintenance edit failed: maintenanceID not in result for '{maintenance_name}'. "
          f"Result: {result}"
        )
      logger.info(f"Editing maintenance '{elt}', id={id}, result: {result.get('msg', '')}")
      logger.debug(
        f'Editing maintenance "{elt}", id={str(id) + "/" + str(result.get("maintenanceID", "unkown"))}, result: {result}')
      edited.append(elt)
    except ConfigError:
      # Relancer les erreurs de configuration
      raise
    except Exception as e:
      maintenance_name = thismaintenance.get("name", thismaintenance.get("title", "unknown"))
      logger.error(f'Error editing maintenance: {maintenance_name}, error: {str(e)}')
      result = {}

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

  # if required, maintenance is deleted
  if delete and len(to_delete) > 0:
    for elt in to_delete:
      # CORRECTION BUG: Vérifier que l'élément existe avant d'accéder à [0]
      maintenance_info = existing_maintenance_dict.get(elt)
      if maintenance_info is None:
        logger.warning(f"Maintenance '{elt}' not found in existing maintenance, skipping deletion")
        continue
      maintenance_id = maintenance_info.get('id')
      if maintenance_id is None:
        logger.warning(f"Maintenance '{elt}' has no 'id' field, skipping deletion")
        continue
      result = api.delete_maintenance(id_=maintenance_id)
      logger.info(f"Deleting removed maintenance '{elt}', id={maintenance_id}, result: {result.get('msg', '')}")
      logger.debug(f"Deleting removed maintenance '{elt}', id={maintenance_id}, result: {result}")
      deleted.append(elt)
      existing_maintenance_dict.pop(elt, None)

  logger.info(f'added: {len(added)}, deleted: {len(deleted)}, edited: {len(edited)}')
  logger.debug(f'added: {added}, deleted: {deleted}, edited: {edited}')

  return existing_maintenance_dict


# =============================================================================
# FUNCTION : filter_monitors_for_maintenance
# =============================================================================
def filter_monitors_for_maintenance(
        monitors: List[Dict[str, Any]],
        monitors_list: List[str],
        excluded: List[int],
        excluded_names: List[str],
        existing_groups: Dict[str, Dict[str, Any]],
        existing_monitors: Dict[str, Dict[str, Any]]
) -> List[int]:
  """
  Filter monitors for maintenance according to inclusion/exclusion rules.

  Args:
      monitors: all monitors list
      monitors_list: monitors to include (ou ['all'])
      excluded: list of ID (groups/monitors) to exclude
      excluded_names: monitors names to exclude from maintenance
      existing_groups: Groupes existants
      existing_monitors: Moniteurs existants

  Returns:
      IDs list of filtered monitors
  """
  if not monitors_list:
    return []

  # if monitors_list is 'all', include all but excluded
  if monitors_list and str(monitors_list[0]).lower() == 'all':
    return [
      l['id'] for l in monitors
      if l.get('parent') not in excluded and l['id'] not in excluded
    ]

  # else, include only monitors in the list
  return [
    l['id'] for l in monitors
    if l['name'] in monitors_list
       and l.get('parent') not in excluded
       and l['id'] not in excluded
  ]


# =============================================================================
# FUNCTION : associate_monitors_with_maintenance
# =============================================================================
def associate_monitors_with_maintenance(
        api: UptimeKumaApi,
        maintenance_id: int,
        monitors_id_list: List[int],
        maintenance_title: str
) -> None:
  """
  Associe une liste de moniteurs à une maintenance.

  Args:
      api: Instance de l'API
      maintenance_id: ID de la maintenance
      monitors_id_list: Liste des IDs de moniteurs
      maintenance_title: Titre de la maintenance (pour le logging)
  """
  if not monitors_id_list:
    logger.debug(f"No monitors to associate with maintenance '{maintenance_title}'")
    return

  monitors_id = [{'id': mid} for mid in monitors_id_list]
  result = api.add_monitor_maintenance(id_=maintenance_id, monitors=monitors_id)
  logger.info(
    f"Associated {len(monitors_id)} monitors with maintenance "
    f"'{maintenance_title}', id={maintenance_id}, result: {result.get('msg', '')}"
  )


# =============================================================================
# FUNCTION : processed_monitors_paused
# =============================================================================
def processed_monitors_paused(api: 'UptimeKumaApi', monitors_paused: list[str], dry_run: bool = True):
  if api is None:
    raise ValueError("api must not be None")
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


# =============================================================================
# FUNCTION : import_config_into_kuma
# =============================================================================
def import_config_into_kuma(file_path: str, api: 'UptimeKumaApi' = None, dry_run: bool = False,
                            delete: bool = False) -> None:
  """
  import toml config into uptimekuma
  :param file_path: toml config file path
  :param api: UptimeKumaApi
  :param dry_run: if true do not import
  :param delete: if true, delete monitors not present in toml files

  Handle configuration import into UptimeKuma api.

  :raises:
    ValueError: if api is None
    ConfigError: if configuration is invalid
    APIError: when using uptimeKuma api

  Note:
  this function has no return value, but raise an exception if an error occurs
  """

  # step 1: loading and validating configuration
  logger.info(f"Loading configuration from {file_path}")
  imported_config = load_toml(file_path)

  # fetch 2: Fetch current state
  logger.info("Fetching existing state from API")
  existing = fetch_existing_state(api)

  # step 3 : Traitement des entités indépendantes (status_pages, tags, notifications, groups, docker)
  logger.info("Processing independent entities")
  processed = process_independent_entities(api=api, config=imported_config, existing=existing, delete=delete)

  # step 4 : replace references by names (groupes, docker hosts, notifications)
  logger.info("Resolving references")
  resolve_all_references(imported_config, processed)

  # step 5 : Traitement des moniteurs
  logger.info("Processing monitors")
  monitors_paused, monitor_processed = process_all_monitors(
    api=api,
    config=imported_config,
    existing=existing,
    processed=processed,
    delete=delete,
    dry_run=dry_run
  )

  # Étape 6 : Finalisation
  logger.info("Finalizing import")
  finalize_import(
    api=api,
    config=imported_config,
    existing=existing,
    processed=processed,
    monitors_paused=monitors_paused,
    dry_run=dry_run,
    delete=delete
  )

  logger.info("Configuration import completed successfully")

  # add/edit/delete containers
  # TODO


# =============================================================================
# utils : reformat monitors
# =============================================================================

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
    raise DataFetchError(f"Failed to fetch existing monitors: {e}") from e
  return existing_config, existing_monitors


# =============================================================================
# utils : reformat tags
# =============================================================================

def get_tags(api: UptimeKumaApi | None) -> list[Any] | tuple[list[Any], dict[Any, dict]]:
  existing_tags = []
  existing_tags_id = {}

  if api is None:
    return existing_tags, existing_tags_id

  try:
    existing_tags = api.get_tags()
  except Exception as e:
    logger.error(f"Failed to get existing tags: {e}")
    raise DataFetchError(f"Failed to fetch existing tags: {e}") from e

  existing_tag_names = list([t['name'] for t in existing_tags])
  existing_tags_id = {t['id']: t for t in existing_tags}

  logger.info(f'existing_tags: {len(existing_tags)}, existing_tags_id: {len(existing_tags_id.keys())}')
  logger.debug(f'existing_tags:  {[v['name'] for k, v in existing_tags_id.items()]}')

  logger.debug(f'unique tags: {existing_tags}, existing_tags_id: {existing_tags_id}')

  return existing_tags, existing_tags_id


# =============================================================================
# main
# =============================================================================

def main():
  """
  Main entrypoint.
   - Configure proprement le logger
  - Gère les erreurs de manière cohérente
  - Retourne des codes de sortie standard
  """

  # set logger
  format_str = '%(asctime)s - %(levelname)s - %(name)s [%(funcName)s][%(lineno)d] - %(message)s'
  formatter = logging.Formatter(format_str)
  logging.basicConfig(format=format_str, level=logging.INFO)
  logger = logging.getLogger(__name__)
  logger.setLevel(logging.INFO)

  # Args parsing
  p = argparse.ArgumentParser(description="Import monitors from TOML into UptimeKuma via UptimeKumaApi")
  p.add_argument("--file", "-f", help="TOML file path", default="kuma.toml")
  p.add_argument("--api-url", "-a", help="UptimeKuma API URL or connection string", default="http://localhost:3001")
  p.add_argument("--logfile", "-l", help="", default=False, action="store_true")
  p.add_argument("--username", "-u", help="API username", required=True)
  p.add_argument("--password", "-p", help="API password", required=True)
  p.add_argument("--token", "-t", help="API token (alternative to username/password)")
  p.add_argument("--dry-run", action="store_true", help="Don't call API; just display actions")
  p.add_argument("--verbose", "-v", help="mode verbose", default=False, action="store_true")
  p.add_argument("--delete", "-d", help="delete notifications, groups, monitors not defined in toml file",
                 default=False, action="store_true")
  args = p.parse_args()

  # args processing
  log_level = logging.INFO
  if args.verbose:
    log_level = logging.DEBUG

  if args.username and not args.password:
    logger.error("When using --username you must provide --password.")
    raise ConfigError(f'When using --username you must provide --password')
  if args.password and not args.username:
    logger.error("When using --password you must provide --username.")
    raise ConfigError(f'When using --password you must provide --username.')

  if args.logfile:
    # shandler = logging.StreamHandler(sys.stdout)
    # shandler.setFormatter(formatter)
    # shandler.setLevel(log_level)
    logger.debug(f'Writing logs to {CDIR}/kuma_load.log')
    fhandler = logging.FileHandler(filename=CDIR + "/kuma_load.log", mode='w')
    fhandler.setLevel(log_level)
    fhandler.setFormatter(formatter)
    # logger.addHandler(shandler)
    logger.addHandler(fhandler)

  logger.setLevel(log_level)

  # Initialisation API
  api = None
  exit_code = 0
  token = ""

  ssl_true = True if args.api_url.startswith("https://") else False
  try:
    api = UptimeKumaApi(url=args.api_url, ssl_verify=ssl_true, timeout=20)

    if args.token:
      token = args.token

    token = get_token_from_kuma_api(kuma_api=api, token=token, username=args.username, password=args.password)
    logger.debug(f'token: {token}')

    if token is None:
      logger.error(f'Error while operating with a token on api')
      raise APIError("Failed to authenticate with UptimeKuma API")

    result = api.get_database_size()
    logger.info(f'Database size: {result["size"]}')
    result = api.need_setup()
    logger.info(f'need setup: {result}')
    result = api.info()
    logger.info(f'info: {result}')
    # result = api.uptime()
    # logger.info(f'uptime: {result}')

    import_config_into_kuma(api=api, file_path=CDIR + os.sep + args.file, dry_run=args.dry_run, delete=args.delete)

    logger.info("Import completed successfully")
    exit_code = 0

  except ConfigError as e:
    logger.error(f"Configuration error: {e}")
    exit_code = 1

  except APIError as e:
    logger.error(f"API error: {e}")
    exit_code = 2

  except KumaLoadError as e:
    logger.error(f"Import error: {e}")
    exit_code = 3

  except Exception as e:
    logger.exception(f"Unexpected error: {e}")
    exit_code = 4

  finally:
    if api is not None:
      try:
        result = api.disconnect()
        logger.debug(f'result: {result}')

      except Exception as e:
        logger.warning(f"Error disconnecting API: {e}")

  sys.exit(exit_code)


if __name__ == "__main__":
  main()
