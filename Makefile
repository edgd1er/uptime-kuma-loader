# Makefile

# Valeurs communes
HOST := holdom4.mission.lan
PORT := 2376
ENDPOINT := /containers/json?all=true
URL := https://$(HOST):$(PORT)$(ENDPOINT)
PYTHONBIN := .venv/bin/python3

# Chemins par défaut (peuvent être surchargés en ligne de commande)
# Chemins des certificats (communs)
CA_PEM ?= /app/data/docker-tls/ca.pem
CERT_PEM ?= /app/data/docker-tls/cert.pem
KEY_PEM ?= /app/data/docker-tls/key.pem

# Alternatifs fournis dans les exemples originaux (réutilisables)
TRAefIK_DIR := ../certificates/intermediateCA
TRAefIK_CA_CERT := $(TRAefIK_DIR)/certs/traefik_client.cert.pem
TRAefIK_CLIENT_CERT := $(TRAefIK_DIR)/certs/traefik_client.cert.pem
TRAefIK_CLIENT_KEY := $(TRAefIK_DIR)/private/traefik_client.key.pem

# Cibles spécifiques

.PHONY: all docker_h4 docker_h2 docker_r2 docker_omv docker_local combined generic kuma kuma3

all: docker_h4 docker_h2 docker_omv docker_local combined kuma kuma3


docker_h4:
	@HOST=holdom4.mission.lan; URL="https://$$HOST:$(PORT)$(ENDPOINT)"; \
	echo "Host: $$HOST: $$URL"; \
	curl -s --cert "$(TRAefIK_CLIENT_CERT)" --key "$(TRAefIK_CLIENT_KEY)" "$$URL" | jq -r ".[].Names| @csv"

# Autre hôte avec autre paire de certificats (exemple)
docker_h3:
	@HOST=holdom3.mission.lan; URL="https://$$HOST:$(PORT)$(ENDPOINT)"; \
	echo "Host: $$HOST: $$URL"; \
	curl -s --cert "$(TRAefIK_CLIENT_CERT)" --key "$(TRAefIK_CLIENT_KEY)" "$$URL" | jq -r ".[].Names| @csv"

docker_h2:
	@HOST=holdom2.mission.lan; URL="https://$$HOST:$(PORT)$(ENDPOINT)"; \
	echo "Host: $$HOST: $$URL"; \
	curl -s --cert "$(TRAefIK_CLIENT_CERT)" --key "$(TRAefIK_CLIENT_KEY)" "$$URL" | jq -r ".[].Names| @csv"

docker_r2:
	@HOST=r2tic.mission.lan; URL="https://$$HOST:$(PORT)$(ENDPOINT)"; \
	echo "Host: $$HOST: $$URL"; \
	curl -s --cert "$(TRAefIK_CLIENT_CERT)" --key "$(TRAefIK_CLIENT_KEY)" "$$URL" | jq -r ".[].Names| @csv"

docker_omv:
	@HOST=omv.mission.lan; URL="https://$$HOST:$(PORT)$(ENDPOINT)"; \
	echo "Host: $$HOST: $$URL"; \
	curl -s --cert "$(TRAefIK_CLIENT_CERT)" --key "$(TRAefIK_CLIENT_KEY)" "$$URL" | jq -r ".[].Names| @csv"
# Exemple utilisant les certificats dans /app/data
docker_local:
	@HOST= holdom4.mission.lan;
	URL := https://$(HOST):$(PORT)$(ENDPOINT)
	@echo "Host: $(HOST)"
	curl -s --cert "$(APPDATA_CERT)" --key "$(APPDATA_KEY)" "$(URL)"
app_data:
	@echo "Running app_data..."
	docker compose exec kuma curl -v --cert $(CERT_PEM) --key $(KEY_PEM) --cacert  $(CA_PEM) "$(URL)"

combined:
	@echo "Running combined (CA + cert + key)..."
	curl --cacert /app/data/docker-tls/ca.pem \
	     --cert /app/data/docker-tls/cert.pem \
	     --key /app/data/docker-tls/key.pem \
	     "$(URL)"

# cible générique utilisant les certificats communs (CERT_PEM/KEY_PEM/CA_PEM)
# Exemple: make generic HOST=myhost.local
generic:
	URL := https://$(HOST):$(PORT)$(ENDPOINT)
	@if [ -z "$(CERT_PEM)" ] || [ -z "$(KEY_PEM)" ]; then \
	  echo "ERROR: CERT_PEM and KEY_PEM must be set"; exit 1; \
	fi
	@echo "URL=$(URL) CA_PEM=$(CA_PEM) CERT_PEM=$(CERT_PEM) KEY_PEM=$(KEY_PEM)"
	@if [ -n "$(CA_PEM)" ]; then \
	  curl --cacert "$(CA_PEM)" --cert "$(CERT_PEM)" --key "$(KEY_PEM)" "$(URL)"; \
	else \
	  curl --cert "$(CERT_PEM)" --key "$(KEY_PEM)" "$(URL)"; \
	fi

fix_api:
	@$(PYTHONBIN) -m pip uninstall -y uptime-kuma-api
	rm -Rf  ./.venv/lib/python3.12/site-packages/uptime-kuma-api
	rm -Rf  ~/.local/lib/python3.12/site-packages/uptime-kuma-api
	#@$(PYTHONBIN) -m pip install git+https://github.com/mmeyer/uptime-kuma-api@v2-support
	@$(PYTHONBIN) -m pip install -e /mnt/DOCS/Working_Directory/uptime-kuma-api/

kuma:
	@@$(PYTHONBIN) ./src/kuma_load/kuma_load.py -f ./kuma.toml --api-url http://localhost:3001 -ukuma -pkuma123 -d -v

kuma3:
	@$(PYTHONBIN) ./src/kuma_load/kuma_load.py -f ./kuma.toml --api-url http://holdom3.mission.lan:3001 -ukuma -pkuma123 -d

kuma4:
	$(PYTHONBIN) ./src/kuma_load/kuma_load.py -f ./kuma.toml -l --api-url http://holdom4.mission.lan:3001 -ukuma -pkuma123 -d -v

docker_test:
		docker compose exec kuma curl -s --cert $(CERT_PEM) --key $(KEY_PEM) --cacert  $(CA_PEM) "https://holdom2.mission.lan:2376/containers/json?all=true" | jq "length"
		docker compose exec kuma curl -s --cert $(CERT_PEM) --key $(KEY_PEM) --cacert  $(CA_PEM) "https://holdom3.mission.lan:2376/containers/json?all=true" | jq "length"
		docker compose exec kuma curl -s --cert $(CERT_PEM) --key $(KEY_PEM) --cacert  $(CA_PEM) "https://holdom4.mission.lan:2376/containers/json?all=true" | jq "length"
		docker compose exec kuma curl -s --cert $(CERT_PEM) --key $(KEY_PEM) --cacert  $(CA_PEM) "https://omv.mission.lan:2376/containers/json?all=true" | jq "length"
		docker compose exec kuma curl -s --cert $(CERT_PEM) --key $(KEY_PEM) --cacert  $(CA_PEM) "https://holdom2.mission.lan:2376/containers/json?all=true" | jq "length"

# Cibles pour les tests
.PHONY: test test-verbose test-coverage test-failed

# Lancer tous les tests (résumé)
test:
	@echo "Lancement de tous les tests..."
	@PYTHONPATH=src $(PYTHONBIN) -m pytest src/tests/ --tb=no

# Lancer tous les tests avec sortie détaillée
test-verbose:
	@echo "Lancement de tous les tests avec détails..."
	@PYTHONPATH=src $(PYTHONBIN) -m pytest src/tests/ -v

# Lancer les tests avec couverture de code (nécessite pytest-cov)
test-coverage:
	@echo "Lancement des tests avec couverture de code..."
	@if $(PYTHONBIN) -m pip list --version 2>/dev/null | grep -q pytest-cov; then \
		PYTHONPATH=src $(PYTHONBIN) -m pytest src/tests/ --cov=src --cov-report=term --tb=no -q; \
	else \
		echo "ERREUR: pytest-cov n'est pas installé. Installez-le avec: pip install pytest-cov"; \
		exit 1; \
	fi

# Lancer uniquement les tests qui échouent
test-failed:
	@echo "Lancement des tests qui échouent..."
	@PYTHONPATH=src $(PYTHONBIN) -m pytest src/tests/ -v --last-failed