# Uptime-kuma loader

## Description

From toml file, create or update a uptime-kuma site.
The script is based on uptime-kuma-api's module.

implemented:
* monitor
* tags
* groups

not implemented:
* all the rest

## Syntax TOML to define monitors

Main points:
- UTF-8 encoded file, extension .toml.
- Several monitors defined with repeated tables [[monitor]].
- [[ monitor ]], top level key define a table having at minimum name and [type](https://uptime-kuma-api.readthedocs.io/en/latest/api.html#uptime_kuma_api.MonitorType).
- groups are also a monitor which type is group.
- Comments supported with #.
- Native types TOML : string, integer, boolean, array, table, multiline string ("""...""").

Structure minimale d'un monitor
- Chaque monitor doit contenir au minimum :
  - name (string) — nom unique du monitor
  - type (string) — un des types valides (voir Enum)

Minimal config
[[monitor]]
name = "Monitor A"
type = "HTTP"

Supported values are the one from the api: https://uptime-kuma-api.readthedocs.io/en/latest/api.html

./kuma_load.py -a http://localhost:3001 -u admin -ppassword -v

- name : string — nom du monitor (obligatoire)
- type : string — type du monitor (obligatoire). Valeurs valides :
  GROUP, HTTP, PORT, PING, KEYWORD, JSON_QUERY, GRPC_KEYWORD, DNS, DOCKER, REAL_BROWSER, PUSH, STEAM, GAMEDIG, MQTT, KAFKA_PRODUCER, SQLSERVER, POSTGRES, MYSQL, MONGODB, RADIUS, REDIS, TAILSCALE_PING
- url : string — URL complète pour HTTP/REAL_BROWSER/JSON_QUERY
- host : string — nom d'hôte ou adresse IP (PORT, PING, DNS, etc.)
- port : integer — port réseau
- interval : integer — intervalle en secondes
- timeout : integer — timeout en secondes
- enabled : boolean — true/false
- tags : array[string] — ex: ["prod","api"]
- notification_ids : array[integer] — identifiants de notification
- ignore_ssl : boolean — ignorer erreur certificat (HTTP/REAL_BROWSER)
- http_method : string — "GET","POST",...
- http_headers : table — paires clé=valeur, ex: http_headers = { Authorization = "Bearer abc", Accept = "application/json" }
- http_body : string (peut être multiline) — corps pour POST/PUT
- auth_method : string — méthode d'authentification. Valeurs valides : NONE, HTTP_BASIC, NTLM, MTLS, OAUTH2_CC
- username : string — pour HTTP_BASIC/NTLM
- password : string — pour HTTP_BASIC/NTLM
- oauth2_token_url : string — pour OAUTH2_CC
- oauth2_client_id : string
- oauth2_client_secret : string
- keyword : string — mot/clause recherché (KEYWORD, GRPC_KEYWORD)
- json_path : string — chemin JSON à interroger (JSON_QUERY)
- expected_status : integer — code HTTP attendu
- expected_text : string — texte attendu dans la réponse
- group_id : integer — id du groupe parent (GROUP)
- heartbeat_url : string — pour PUSH monitors
- steam_appid : integer — pour STEAM
- docker_host : string — hôte docker (DOCKER)
- maintenance_ids : array[integer] — ids de maintenance
- notes : string (multiline autorisé)
- custom_fields : table — paires nom=valeur custom

Représentation TOML recommandée

- Définir plusieurs monitors :
[[monitor]]
name = "Site principal"
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
name = "DB locale"
type = "PORT"
host = "10.0.0.5"
port = 5432
interval = 120
tags = ["db","postgres"]

- Exemple avec chaîne multi‑ligne :
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

Validation et contraintes
- name doit être non vide et idéalement unique (le script compare par name).
- type et auth_method validés contre les listes d'enum.
- interval, timeout, port doivent être des entiers.
- tags doit être un tableau de strings.
- notification_ids et maintenance_ids doivent être tableaux d'entiers.
- http_headers et custom_fields doivent être tables/dictionnaires.
- Pour auth_method spécifiques, champs requis :
  - HTTP_BASIC → username et password obligatoires.
  - OAUTH2_CC → oauth2_token_url, oauth2_client_id, oauth2_client_secret obligatoires.

Formats alternatifs acceptés par le script
- Top-level "monitors" comme tableau : monitors = [ {name="A", type="HTTP", ...}, {...} ]
- Fichier contenant une seule table monitor sans wrapper si il a name+type.

Bonnes pratiques
- Utiliser des noms de monitors uniques et explicites.
- Stocker secrets (passwords, client_secret) de façon sécurisée; le fichier TOML contient des secrets en clair.
- Préférer --dry-run du script pour vérifier la conversion avant d'appliquer.
