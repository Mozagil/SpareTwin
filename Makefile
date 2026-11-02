# SpareTwin geliştirme komutları. `make` yazınca liste çıkar.
.DEFAULT_GOAL := help
PY ?= python

help: ## Komut listesi
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*## "}{printf "  make %-12s %s\n", $$1, $$2}'

setup: ## Python ve Node paketlerini kur, .env oluştur
	$(PY) -m pip install -e "backend[dev]"
	cd frontend && npm ci --no-audit --no-fund
	@test -f .env || cp .env.example .env

check: # Kurulum kontrolü (diğer komutlar kullanır)
	@$(PY) -c "import sparetwin" 2>/dev/null || { echo; echo "  Python paketleri kurulu değil. Önce: make setup"; echo; exit 1; }
	@test -d frontend/node_modules || { echo; echo "  Frontend paketleri kurulu değil. Önce: make setup"; echo; exit 1; }

ports: # 5173 ve 8000 boş mu?
	@$(PY) -c "import socket,sys; busy=[p for p in (5173,8000) if socket.socket().connect_ex(('127.0.0.1',p))==0]; busy and sys.exit(f'\n  Port dolu: {busy}. Arka planda eski bir sunucu çalışıyor. Önce: make stop\n')"

stop: ## Arka planda kalan API ve frontend sunucularını kapat
	@-pkill -f "[u]vicorn sparetwin" && echo "API durduruldu" || true
	@-pkill -f "[n]ode .*[v]ite" && echo "Frontend durduruldu" || true

db: check ## Veritabanını başlat / hazır olmasını bekle
	@if [ -n "$$SPARETWIN_DEVCONTAINER" ]; then \
		$(PY) -m sparetwin.cli wait-db; \
	else \
		docker compose up -d --wait db; \
	fi

reset: db ## Şemayı sıfırla + demo veri yükle
	$(PY) -m sparetwin.cli reset-dev
	$(PY) -m sparetwin.cli seed-demo

api: db ## API'yi otomatik yeniden yüklemeyle çalıştır (http://localhost:8000/docs)
	$(PY) -m uvicorn sparetwin.main:create_app --factory --reload --host 0.0.0.0 --port 8000 --reload-dir backend/sparetwin

web: check ## Frontend geliştirme sunucusu (http://localhost:5173)
	cd frontend && npm run dev

dev: db ports ## API + frontend birlikte (Ctrl+C ikisini de durdurur)
	@echo "Uygulama: Ports sekmesinde 5173 · API dokümanı: 8000/docs"
	@$(MAKE) --no-print-directory -j2 api web

test: db ## Tüm testler: backend (sparetwin_test veritabanını siler!) + frontend
	cd backend && $(PY) -m pytest -q
	cd frontend && npm test

build: ## Frontend üretim derlemesi (frontend/dist)
	cd frontend && npm run build

up: ## Veritabanı + API'yi imaj olarak çalıştır (Codespace dışında, Docker gerekir)
	docker compose --profile full up -d --build --wait

down: ## Tüm container'ları durdur
	docker compose --profile full down

prototype: ## İlk tasarım taslağı (statik, demo verili) 8080 portunda
	$(PY) -m http.server 8080 --directory prototype

.PHONY: help setup check ports stop db reset api web dev test build up down prototype
