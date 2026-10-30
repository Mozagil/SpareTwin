# SpareTwin geliştirme komutları. `make` yazınca liste çıkar.
.DEFAULT_GOAL := help
PY ?= python

help: ## Komut listesi
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*## "}{printf "  make %-12s %s\n", $$1, $$2}'

setup: ## Python paketlerini kur, .env oluştur
	$(PY) -m pip install -e "backend[dev]"
	@test -f .env || cp .env.example .env

db: ## Veritabanını başlat / hazır olmasını bekle
	@if [ -n "$$SPARETWIN_DEVCONTAINER" ]; then \
		$(PY) -m sparetwin.cli wait-db; \
	else \
		docker compose up -d --wait db; \
	fi

reset: db ## Şemayı sıfırla + demo veri yükle
	$(PY) -m sparetwin.cli reset-dev
	$(PY) -m sparetwin.cli seed-demo

api: db ## API'yi otomatik yeniden yüklemeyle çalıştır (http://localhost:8000/docs)
	uvicorn sparetwin.main:create_app --factory --reload --host 0.0.0.0 --port 8000 --reload-dir backend/sparetwin

test: db ## Tüm testleri çalıştır (sparetwin_test veritabanını siler!)
	cd backend && $(PY) -m pytest -q

up: ## Veritabanı + API'yi imaj olarak çalıştır (Codespace dışında, Docker gerekir)
	docker compose --profile full up -d --build --wait

down: ## Tüm container'ları durdur
	docker compose --profile full down

prototype: ## Dashboard prototipini 8080 portunda aç
	$(PY) -m http.server 8080 --directory prototype

.PHONY: help setup db reset api test up down prototype
