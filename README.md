# Преемник

Платформа передачи дел: ИИ-интервьюер вытаскивает из уходящего сотрудника неявные знания, эксперт проверяет карточки знаний, преемник получает ответы со ссылками на источники, руководитель видит карту рисков.
Хакатон «Академия финтеха», трек «Эффективность 360».

> Статус: **M0 — каркас**. Работают вход, роли, layout и фоновые задачи; разделы продукта появляются по [плану](docs/plan.md).

## Быстрый старт (Docker)

Нужны Docker с Compose v2.24+ и `make`.

```bash
cp .env.example .env     # для демо можно не менять
make up                  # db, backend, worker, frontend
make seed-demo           # вымышленные демо-данные
```

Откройте http://localhost:3000. Демо-учётки (пароль `demo1234`), на странице входа их можно подставить кликом:

| Роль | Email |
|---|---|
| Руководитель | `manager@demo.local` |
| Эксперт | `expert@demo.local` |
| Преемник | `successor@demo.local` |
| Администратор | `admin@demo.local` |

Полезное: `make logs`, `make ps`, `make down`; API и Swagger — http://localhost:8000/docs; проверка здоровья — http://localhost:8000/api/health.

## Разработка без контейнеров приложения

Нужны [uv](https://docs.astral.sh/uv/) и Node.js 22.

```bash
make install          # зависимости backend и frontend
make dev-backend      # PostgreSQL в docker + backend на :8000 с автоперезагрузкой
make dev-worker       # фоновые задачи (в отдельном терминале)
make dev-frontend     # Vite на :3000, /api проксируется на :8000
```

После изменения API — `make gen-api` (типы для фронтенда из OpenAPI).

## Проверки

```bash
make test        # все тесты: backend (юнит + интеграционные на PostgreSQL) и frontend
make test-unit   # быстрые юнит-тесты backend без БД
make lint        # ruff, import-linter, mypy, eslint, prettier, tsc
```

Тесты не требуют GPU, интернета и ключей: LLM, ASR и эмбеддинги в них — fake-провайдеры.

## Модели

Сейчас реализованы только fake-провайдеры (`LLM_PROVIDER=fake` и т. д. в `.env`). Подключение OpenAI-совместимого сервера (vLLM, Ollama, облако) — этап M1; генеративная часть рассчитана на российские и on-prem модели. `OFFLINE_MODE=true` запрещает обращения к нелокальным адресам.

## Документация

| Файл | О чём |
|---|---|
| [docs/SPEC.md](docs/SPEC.md) | техническое задание |
| [docs/architecture.md](docs/architecture.md) | архитектура: модули, интерфейсы, схема данных, диаграммы |
| [docs/plan.md](docs/plan.md) | план работ по этапам |
| [docs/decisions.md](docs/decisions.md) | журнал решений |
| [docs/story.md](docs/story.md) | что уже сделано |
| [docs/lessons.md](docs/lessons.md) | ошибки и выводы из них |
| [docs/ideas.md](docs/ideas.md) | идеи на потом |

## Структура

```
backend/    FastAPI + worker: app/core (платформа), app/providers (модели), app/modules/<область>
frontend/   React + Vite + TypeScript
seed/       демо-данные
docs/       документация
```
