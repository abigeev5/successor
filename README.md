# Преемник

Платформа передачи дел: ИИ-интервьюер вытаскивает из уходящего сотрудника неявные знания, эксперт проверяет карточки знаний, преемник получает ответы со ссылками на источники, руководитель видит карту рисков.
Хакатон «Академия финтеха», трек «Эффективность 360».

> Статус: **M1 — интервьюер и карточки**. Работают передачи дел, согласие, ИИ-интервью (текст и голос), извлечение карточек с проверкой цитат и проверка карточек экспертом. Ассистент преемника, записи экрана и панель руководителя — следующие этапы ([план](docs/plan.md)).

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

Тесты не требуют GPU, интернета, ключей и скачанных моделей: LLM, ASR и эмбеддинги в них — fake-провайдеры, а реальные провайдеры проверяются на подменённом HTTP.

## Модели: локально через llama.cpp

Без модели (`LLM_PROVIDER=fake`, по умолчанию) приложение работает: интервьюер задаёт заготовленные вопросы, но не понимает ответы и не извлекает карточки. Демо-данные (`make seed-demo`) уже содержат завершённое интервью и карточки.

Чтобы подключить настоящую модель, запустите [llama.cpp](https://github.com/ggml-org/llama.cpp) **на хосте**. В Docker на macOS нет доступа к GPU, поэтому модель в контейнере работала бы слишком медленно (решение D-033).

1. Установите llama.cpp: `brew install llama.cpp` (macOS) или соберите по инструкции проекта (Linux, CUDA).
2. Скачайте GGUF-модели (выбор модели — решение команды, ТЗ п. 17.1). Ориентиры: instruct-модель 7–14B семейства Qwen или T-lite/T-pro в квантовании Q4_K_M/Q5_K_M; для эмбеддингов — GGUF-версия `bge-m3`.
3. Запустите два сервера:
   ```bash
   llama-server -m ./models/llm.gguf --port 8080 -c 16384 --jinja             # генерация
   llama-server -m ./models/bge-m3.gguf --port 8081 --embeddings --pooling cls  # эмбеддинги
   ```
4. В `.env`:
   ```bash
   LLM_PROVIDER=openai_compatible
   EMBEDDINGS_PROVIDER=openai_compatible
   ASR_PROVIDER=faster_whisper
   ```
   Адреса `http://host.docker.internal:8080/v1` и `:8081/v1` уже прописаны в `.env.example`. Если backend запущен без docker (`make dev-backend`), замените их на `http://localhost:…`.
5. `make up` (или перезапустите `make dev-backend`). Проверка: http://localhost:8000/api/health — у `llm` и `embeddings` должно быть `"ok": true`.

Распознавание речи — faster-whisper `small` (D-031). Модель скачивается при первом голосовом ответе (~500 МБ) и хранится в volume `models`. В закрытом контуре укажите в `ASR_MODEL` путь к заранее скачанной папке модели.

`OFFLINE_MODE=true` запрещает обращения к нелокальным адресам: `host.docker.internal`, `localhost` и адреса из частных диапазонов разрешены.

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
