# Преемник — команды разработки. `make help` — список.
SHELL := /bin/bash
COMPOSE := docker compose
DB_PORT ?= 5432
TEST_DATABASE_URL ?= postgresql+psycopg://preemnik:preemnik@localhost:$(DB_PORT)/preemnik_test

.PHONY: help up up-local-llm down logs ps db migrate seed-demo test test-unit test-backend test-frontend \
        lint format gen-api eval dev-backend dev-worker dev-frontend install

help:  ## Показать команды
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*## "}{printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

# --- Docker ---
up:  ## Собрать и поднять всё: db, backend, worker, frontend (http://localhost:3000)
	$(COMPOSE) up -d --build --wait
	@echo "Готово: http://localhost:$${FRONTEND_PORT:-3000}. Демо-данные: make seed-demo"

up-local-llm:  ## То же + LLM и эмбеддинги в контейнерах llama.cpp (GGUF из ./models, см. README)
	$(COMPOSE) --profile local-llm up -d --build --wait

down:  ## Остановить (данные в volume сохраняются)
	$(COMPOSE) --profile local-llm down

logs:  ## Логи всех сервисов
	$(COMPOSE) logs -f --tail=100

ps:  ## Состояние сервисов
	$(COMPOSE) ps

db:  ## Поднять только PostgreSQL (для тестов и локального backend)
	$(COMPOSE) up -d --wait db

migrate:  ## Применить миграции (в контейнере backend)
	$(COMPOSE) run --rm backend alembic upgrade head

seed-demo:  ## Загрузить вымышленные демо-данные (идемпотентно)
	$(COMPOSE) run --rm backend python /app/seed/seed.py

# --- Проверки ---
install:  ## Установить зависимости для локальной разработки (uv, npm)
	cd backend && uv sync
	cd frontend && npm ci

test: db test-backend test-frontend  ## Все тесты (поднимает db в docker)

test-unit:  ## Юнит-тесты backend без БД
	cd backend && uv run pytest tests/unit -q

test-backend:  ## Тесты backend (юнит + интеграционные на PostgreSQL)
	cd backend && REQUIRE_DB=1 TEST_DATABASE_URL=$(TEST_DATABASE_URL) uv run pytest -q

test-frontend:  ## Тесты frontend
	cd frontend && npm test

lint:  ## Линтеры: ruff, import-linter, mypy (мягко), eslint, prettier, tsc
	cd backend && uv run ruff check . && uv run ruff format --check . && uv run lint-imports
	-cd backend && uv run mypy app
	cd frontend && npm run lint && npm run typecheck

format:  ## Автоформатирование
	cd backend && uv run ruff check --fix . && uv run ruff format .
	cd frontend && npm run format

gen-api:  ## Сгенерировать типы API для frontend из OpenAPI backend
	cd backend && uv run python scripts/export_openapi.py
	cd frontend && npm run gen-api

PROVIDER ?= real
eval:  ## Оценка ассистента на демо-наборе → eval/reports/ (без модели: make eval PROVIDER=fake)
	$(COMPOSE) run --rm --user "$$(id -u):$$(id -g)" -v "$(CURDIR)/eval/reports:/app/eval/reports" \
		backend python /app/eval/run_eval.py --provider $(PROVIDER)

# --- Локальная разработка без контейнеров backend/frontend ---
dev-backend: db  ## Backend с автоперезагрузкой на :8000
	cd backend && uv run alembic upgrade head && uv run uvicorn app.main:app --reload --port 8000

dev-worker:  ## Worker локально
	cd backend && uv run python -m app.worker

dev-frontend:  ## Vite dev-сервер на :3000 (проксирует /api на :8000)
	cd frontend && npm run dev
