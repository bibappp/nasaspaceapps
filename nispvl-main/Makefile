.PHONY: dev backend frontend install test build demo smap offline-check lint audit

PY ?= python3.11
VENV := backend/.venv

install: ## Установить зависимости бэкенда и фронтенда
	$(PY) -m venv $(VENV)
	$(VENV)/bin/pip install -q --upgrade pip
	$(VENV)/bin/pip install -q -c backend/constraints.txt -e "backend[dev]"
	cd frontend && npm install

dev: ## Запустить бэкенд (8000) и фронтенд (5173) локально
	@trap 'kill 0' INT TERM EXIT; \
	(cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000) & \
	(cd frontend && npm run dev) & \
	wait

backend:
	cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000

frontend:
	cd frontend && npm run dev

test: ## Юнит-тесты бэкенда
	cd backend && .venv/bin/pytest

build: ## Сборка фронтенда (включает проверку TypeScript strict)
	cd frontend && npm run build

lint:
	cd backend && .venv/bin/ruff check app tests ../scripts

demo: ## Скачать и сохранить данные демо-поля в data/demo (нужен интернет)
	cd backend && .venv/bin/python ../scripts/build_demo.py $(ARGS)

smap: ## Скачать ряд SMAP для демо-поля (нужен EARTHDATA_TOKEN)
	cd backend && .venv/bin/python ../scripts/prefetch_smap.py

offline-check: ## Проверить, что демо проходит до PDF без сети
	cd backend && OFFLINE=1 .venv/bin/python ../scripts/offline_check.py

audit: ## Воспроизводимый аудит модели на демо-поле (без сети) -> docs/audit/
	cd backend && .venv/bin/python ../scripts/audit_model.py
