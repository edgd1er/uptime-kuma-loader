# Uptime-kuma loader

## Description

From toml file, create or update a uptime-kuma site.
The script is based on uptime-kuma-api's module.
updatime-kuma-api had to be updated: `python3 -m pip install git+https://github.com/edgd1er/uptime-kuma-api.git@v2-support`
elements not present in config (toml) or duplicate in database are deleted if -d argument is given.

`pip install .` will install all dependencies

Implemented:
* monitor
* tags
* groups
* notification
* pause/resume
* maintenance

Not implemented (maybe):
* status page
* uptime
* statistics

Not implemented (not planned):
* proxy
* api key
* all the rest

## Syntax TOML to define monitors

Main points:
- UTF-8 encoded file, extension .toml.
- Several monitors defined with repeated tables [[monitor]].
- [[ monitor ]], top level key define a table having at minimum name and [type](https://uptime-kuma-api.readthedocs.io/en/latest/api.html#uptime_kuma_api.MonitorType).
- other top level keys are maintenance, notification, status, docker
- groups are also a monitor which type is group.
- Comments supported with #.
- Native types TOML : string, integer, boolean, array, table, multiline string ("""...""").
- all keys/values are the one listed in [uptime-kuma-api](https://uptime-kuma-api.readthedocs.io/en/latest/api.html)
Some key/value pairs were added as not preset in the "add_monitor" function:
  * group
  * active (true = pause). All groups are unpaused.

Monitor's minimal fields:
  * name (string) — monitor's unique name
  * type (string) — one of the valid types (see [Enum](https://uptime-kuma-api.readthedocs.io/en/latest/api.html#uptime_kuma_api.AuthMethod))

```toml
[[monitor]]
name = "Monitor A"
type = "HTTP"
```

Supported values are the one from the api: https://uptime-kuma-api.readthedocs.io/en/latest/api.html

- name : string — monitor's name (required)
- type : string — monitor's name (required). Expected values:
  GROUP, HTTP, PORT, PING, KEYWORD, JSON_QUERY, GRPC_KEYWORD, DNS, DOCKER, REAL_BROWSER, PUSH, STEAM, GAMEDIG, MQTT, KAFKA_PRODUCER, SQLSERVER, POSTGRES, MYSQL, MONGODB, RADIUS, REDIS, TAILSCALE_PING
- url : string — complete URL for HTTP/REAL_BROWSER/JSON_QUERY
- host : string — hostname or ip (PORT, PING, DNS, etc.)
- port : integer — port
- interval : integer — interval in seconds
- timeout : integer — timeout in seconds
- enabled : boolean — true/false
- tags : array[string] — ex: ["prod","api"]
- notification_ids : array[integer] — notification ids
- ignore_ssl : boolean — ignore certificats error (HTTP/REAL_BROWSER)
- http_method : string — "GET","POST",...
- http_headers : table — keys, values, ex: http_headers = { Authorization = "Bearer abc", Accept = "application/json" }
- http_body : string (peut être multiline) — body for POST/PUT
- auth_method : string — authentification method: expected values: NONE, HTTP_BASIC, NTLM, MTLS, OAUTH2_CC
- username : string — for HTTP_BASIC/NTLM
- password : string — for HTTP_BASIC/NTLM
- oauth2_token_url : string — for OAUTH2_CC
- oauth2_client_id : string
- oauth2_client_secret : string
- keyword : string — searched word phrase (KEYWORD, GRPC_KEYWORD)
- json_path : string — JSON path to query (JSON_QUERY)
- expected_status : integer — expected HTTP code
- expected_text : string — expected text in body's response
- group_id : integer — parent group's id (GROUP)
- heartbeat_url : string — for PUSH monitors
- steam_appid : integer — for STEAM
- docker_host : string — docker host (DOCKER)
- maintenance_ids : array[integer] — maintenance ids
- notes : string (multiline allowed)
- custom_fields : table — k,v pairs name=valeur

TOML monitor config example:

```toml
[[monitor]]
name = "main site"
type = "HTTP"
url = "https://example.com/health"
interval = 60
timeout = 10
enabled = true
tags = ["prod","frontend"]
notification_ids = [1,2]
http_headers = { Accept = "application/json" }
expected_status = 200

[[monitor]]
name = "local DB "
type = "PORT"
host = "10.0.0.5"
port = 5432
interval = 120
tags = ["db","postgres"]

[[monitor]]
name = "API token check"
type = "HTTP"
url = "https://api.example.com/token"
http_method = "POST"
http_headers = { "Content-Type" = "application/json" }
http_body = """
{
  "client": "abc",
  "secret": "xyz"
}
"""
```

Validation et contraintes
- name doit être non vide et idéalement unique (le script compare par name).
- types and auth_method are validated with enum lists.
- interval, timeout, port are to be integers.
- tags is a string table.
- notification_ids and maintenance_ids are integer's array.
- http_headers and custom_fields should be tables/dictionnaries.
- for auth_method, required fiekds:
  - HTTP_BASIC → username and password required.
  - OAUTH2_CC → oauth2_token_url, oauth2_client_id, oauth2_client_secret required.

Accepted alternate formats:
- Top-level "monitors" as tables: monitors = [ {name="A", type="HTTP", ...}, {...} ]
- file with only name and type without header/wrapper.

Best practices
- Use explicit and unique names.
- secrets (passwords, client_secret) are stored in clear text.
- Use --dry-run to check what would be done.


curl --cert ../certificates/intermediateCA/certs/traefik_client.cert.pem --key ../certificates/intermediateCA/private/traefik_client.key.pem https://holdom4.mission.lan:2376/containers/json?all=true

curl --cert ../certificates/intermediateCA/certs/traefik_omv.cert.pem --key ../certificates/intermediateCA/private/traefik_omv.key.pem https://holdom4.mission.lan:2376/containers/json?all=true

curl --cert /app/data/docker-tls/mission.lan/cert.pem --key /app/data/docker-tls/mission.lan/key.pem https://holdom4.mission.lan:2376/containers/json?all=true

curl --cacert /app/data/docker-tls/ca.pem --cert /app/data/docker-tls/cert.pem --key /app/data/docker-tls/key.pem https://holdom4.mission.lan:2376/containers/json?all=true


./kuma_load.py -a http://holdom3.mission.lan:3001 -ukuma -pkuma123 -d

./kuma_load.py -a http://localhost:3001 -ukuma -pkuma123 -d
