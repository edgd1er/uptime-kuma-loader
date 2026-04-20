import pytest
from unittest.mock import Mock

# Adapter l'import selon ton projet
from src.kuma_load import create_update_notification

class DummyApi:
  def __init__(self, notifications):
    self._notifications = notifications
    self.edit_notification = Mock()
    self.add_notification = Mock()
  def get_notifications(self):
    return self._notifications

def test_create_update_notification_returns_empty_when_no_config():
  assert create_update_notification(api=None, config=None) == {}

def test_create_update_notification_calls_edit_when_names_match():
  # arrange: API retourne une notification avec same name as config
  api = DummyApi({'name': 'notification 1'})
  # make edit_notification return a sentinel
  api.edit_notification.return_value = {'status': 'edited'}
  config = {'name': 'notification 1'}
  # act
  res = create_update_notification(api=api, config=config)
  # assert edit called, add not called, and return is None (function doesn't return explicit result)
  api.edit_notification.assert_called_once()
  api.add_notification.assert_not_called()
  assert res is None or res == api.edit_notification.return_value

def test_create_update_notification_calls_add_when_names_differ():
  api = DummyApi({'name': 'other name'})
  api.add_notification.return_value = {'status': 'added'}
  config = {'name': 'notification 1'}
  res = create_update_notification(api=api, config=config)
  api.add_notification.assert_called_once()
  api.edit_notification.assert_not_called()
  assert res is None or res == api.add_notification.return_value

def test_create_update_notification_uses_payload_structure():
  api = DummyApi({'name': 'other name'})
  api.add_notification.return_value = {'status': 'added'}
  config = {'name': 'notification 1'}
  create_update_notification(api=api, config=config)
  # inspect the payload passed to add_notification
  assert api.add_notification.call_count == 1
  kwargs = api.add_notification.call_args.kwargs
  assert 'payload' in kwargs
  payload = kwargs['payload']
  # basic payload shape checks
  assert payload.get('active') is True
  assert payload.get('applyExisting') is True
  assert payload.get('name') == 'notification 1' or isinstance(payload.get('name'), str)
  assert 'type' in payload
  assert 'pushAPIKey' in payload

def test_create_update_notification_edit_called_with_id_and_payload():
  api = DummyApi({'name': 'notification 1'})
  api.edit_notification.return_value = {'status': 'edited'}
  config = {'name': 'notification 1'}
  create_update_notification(api=api, config=config)
  assert api.edit_notification.call_count == 1
  args, kwargs = api.edit_notification.call_args
  # function calls edit_notification(id_=config['name'], payload=payload)
  # The mock captures keyword args
  assert 'id_' in kwargs
  assert kwargs['id_'] == config['name']
  assert 'payload' in kwargs
  assert kwargs['payload'].get('type') == 'PushByTechulus'
