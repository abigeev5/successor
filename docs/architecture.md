# Преемник — архитектура MVP

> Статус: **согласовано 2026-10-17** (решения D-001…D-011 в `decisions.md`). Отклонения от ТЗ собраны в разделе 9.
> Код и идентификаторы — на английском, документация и тексты интерфейса — на русском.

Содержание:
1. Принципы
2. Варианты использования (use cases)
3. Компоненты и модули
4. Модель данных (диаграмма классов)
5. Ключевые интерфейсы (точки расширения)
6. Диаграммы последовательности
7. Диаграммы состояний
8. Структура репозитория
9. Отклонения от ТЗ и открытые вопросы
10. Как вносить типовые изменения

---

## 1. Принципы

1. **Модульный монолит.** Один Python-пакет `app`, который запускается двумя процессами: `backend` (FastAPI) и `worker` (фоновые задачи). Микросервисы для хакатона дороже, чем приносят пользы.
2. **Модули по предметным областям, а не по техническим слоям.** Всё про интервью лежит в `modules/interview/`: модели, схемы, сервис, роутер, чистая логика. Изменение одной функции затрагивает одну папку.
3. **Внутри модуля — три слоя:**
   - `router` — только HTTP: разбор запроса, права, вызов сервиса, ответ;
   - `service` — сценарий: транзакция, вызовы провайдеров, публикация событий;
   - `domain` — чистые функции без ввода-вывода (планировщик, покрытие, риск, валидация цитат, RRF, разбор утверждений). Здесь основная логика и основные юнит-тесты.
4. **Зависимости только сверху вниз** (раздел 3.2). Нижний модуль сообщает верхнему что-то только через **события** или **зарегистрированные интерфейсы**. Прямых импортов вверх нет.
5. **Все внешние модели — за интерфейсами** (`providers/`): LLM, эмбеддинги, ASR, OCR, VLM, файловое хранилище. Реализация выбирается в конфиге, для тестов есть fake-реализации.
6. **Фоновые задачи — через таблицу `jobs`.** Событие и задача записываются в одной транзакции, поэтому задача не теряется, если процесс упал.
7. **Промпты — версионированные файлы.** Версия промпта пишется в логи и в отчёты eval, чтобы прогоны можно было сравнивать.
8. **Без лишнего:** нет DDD-агрегатов, CQRS, Celery, LangChain. Абстракция появляется только там, где её точно будут подменять (провайдеры, источники, хранилище, удаление данных).

---

## 2. Варианты использования

### 2.1 Диаграмма

```
                         ┌──────────────────────────── Преемник ────────────────────────────┐
                         │                                                                  │
  ┌─────────┐            │  (UC-00 Вход/выход)                                              │
  │ Все     │────────────┤                                                                  │
  └─────────┘            │                                                                  │
                         │  (UC-01 Создать передачу дел)      (UC-04 Карта рисков)          │
  ┌─────────┐            │  (UC-02 Процессы и знающие)        (UC-05 Метрики + CSV)         │
  │Руковод- │────────────┤  (UC-03 Прогресс передачи)         (UC-06 Пробелы без эксперта)  │
  │итель    │            │  (UC-07 Завершить передачу)        (UC-08 Журнал аудита)         │
  └─────────┘            │                                                                  │
                         │  (UC-10 Согласие: принять/отозвать)                              │
  ┌─────────┐            │  (UC-11 Интервью текстом) ──include──► (UC-13 Карта обязанностей)│
  │Эксперт  │────────────┤  (UC-12 Голосовой ответ) ──extend──► (UC-11)                     │
  │         │            │  (UC-14 Пауза / след. процесс / завершить)                       │
  │         │            │  (UC-15 Запись экрана / загрузка видео)                          │
  │         │            │  (UC-16 Проверить карточку) ──extend──► (UC-16a Объединить дубль)│
  │         │            │  (UC-17 Ответить на пробел)    (UC-18 Удалить свои данные)       │
  │         │            │  (UC-19 Создать карточку вручную)                                │
  └─────────┘            │                                                                  │
                         │  (UC-20 Задать вопрос) ──extend──► (UC-23 Спросить эксперта)     │
  ┌─────────┐            │  (UC-21 Открыть источник)   (UC-22 Оценить ответ)                │
  │Преемник │────────────┤  (UC-24 База знаний)        (UC-25 Уведомление о закрытом пробеле)│
  └─────────┘            │                                                                  │
  ┌─────────┐            │  (UC-30 Пользователи)  (UC-31 Подразделения)  (UC-32 Здоровье)   │
  │Админ    │────────────┤                                                                  │
  └─────────┘            │  (UC-40 Извлечь карточки)  (UC-41 Обработать запись)             │
  ┌─────────┐            │  (UC-42 Индексировать карточку)  (UC-43 Чистка медиа по сроку)   │
  │Система  │────────────┤  (UC-44 Прогон eval)                                             │
  │(worker) │            │                                                                  │
  └────┬────┘            └──────────────────────────────────────────────────────────────────┘
       │ использует
  ┌────▼─────────────────────┐
  │ LLM · ASR · Эмбеддинги · │  внешние/локальные модели
  │ OCR · VLM                │
  └──────────────────────────┘
```

### 2.2 Список

| ID | Актор | Вариант использования | Модуль | Приоритет | Этап |
|---|---|---|---|---|---|
| UC-00 | все | Вход по email/паролю, выход, «кто я» | identity | Must | M0 |
| UC-01 | руководитель | Создать передачу дел (эксперт, преемник, процессы, причина, дедлайн) | handovers | Must | M1 |
| UC-02 | руководитель | Вести процессы подразделения и список знающих | org | Must | M1 |
| UC-03 | руководитель | Смотреть прогресс передачи | analytics | Must | M2 |
| UC-04 | руководитель | Смотреть карту рисков | analytics | Must | M4 |
| UC-05 | руководитель | Смотреть метрики, выгружать CSV | analytics | Must | M4 |
| UC-06 | руководитель | Закрыть пробел или переназначить его другому эксперту | gaps | Must | M2 |
| UC-07 | руководитель | Завершить или отменить передачу | handovers | Must | M1 |
| UC-08 | руководитель, админ | Смотреть журнал аудита | audit | Should | M4 |
| UC-10 | эксперт | Принять согласие; отозвать согласие | privacy | Must | M1 |
| UC-11 | эксперт | Пройти интервью текстом | interview | Must | M1 |
| UC-12 | эксперт | Ответить голосом (запись → распознавание → правка → отправка) | interview | Must | M1 |
| UC-13 | эксперт | Подтвердить карту обязанностей (процессы, частота, критичность) | interview + org | Must | M1 |
| UC-14 | эксперт | Поставить на паузу, перейти к следующему процессу, завершить сессию | interview | Must | M1 |
| UC-15 | эксперт | Записать экран с комментарием или загрузить видео | recordings | Should | M3 |
| UC-16 | эксперт | Проверить карточку: подтвердить, поправить, отклонить, объединить | knowledge | Must | M1 |
| UC-17 | эксперт | Ответить на пробел текстом или голосом | gaps | Must | M2 |
| UC-18 | эксперт | Удалить свои данные или отдельную запись | privacy | Must | M4 |
| UC-19 | эксперт | Создать карточку вручную | knowledge | Should | M2 |
| UC-20 | преемник | Задать вопрос ассистенту | assistant | Must | M2 |
| UC-21 | преемник | Открыть карточку и её первоисточник (цитата, видео с секунды) | knowledge | Must | M2 |
| UC-22 | преемник | Оценить ответ («помогло / не помогло» + комментарий) | assistant | Must | M2 |
| UC-23 | преемник | Отправить вопрос эксперту (создать пробел вручную) | gaps | Must | M2 |
| UC-24 | преемник, эксперт, руководитель | Смотреть базу знаний с фильтрами и поиском | knowledge + search | Must | M2 |
| UC-25 | преемник | Получить уведомление, что на его пробел ответили | gaps | Should | M2 |
| UC-30 | админ | Управлять пользователями | identity | Must (минимально) | M0 |
| UC-31 | админ | Управлять подразделениями | org | Must (минимально) | M0 |
| UC-32 | админ | Проверить доступность БД и моделей (`/health`) | core | Must | M0 |
| UC-40 | система | Извлечь черновики карточек из сессии интервью | knowledge | Must | M1 |
| UC-41 | система | Обработать запись: аудио → транскрипт → шаги → скриншоты → размытие ПДн → черновик | recordings | Should | M3 |
| UC-42 | система | Проиндексировать подтверждённую карточку, убрать из индекса отклонённую | search | Must | M2 |
| UC-43 | система | Удалить сырые медиа по истечении срока хранения | privacy | Should | M4 |
| UC-44 | разработчик / CI | Прогнать eval ассистента и извлечения | eval | Must | M2 |

### 2.3 Подробные сценарии ключевых вариантов

**UC-11 Пройти интервью**
- Предусловие: эксперт входит в передачу, согласие принято (иначе 403 «Сначала примите согласие на запись»).
- Основной поток:
  1. Эксперт открывает сессию, система задаёт вопрос фазы `intro`.
  2. Эксперт отвечает.
  3. Система анализирует ответ (LLM), обновляет покрытие аспектов, детерминированно выбирает следующий шаг и формулирует вопрос (LLM).
  4. Эксперт видит вопрос и обновлённую панель покрытия. Шаги 2–4 повторяются.
- Альтернативы:
  - 3а. Ответ общий → уточняющий вопрос «приведите пример».
  - 3б. Упомянут новый процесс → он попадает в список кандидатов, эксперт подтверждает его (UC-13).
  - 3в. «Не знаю / так не бывает» → аспект помечается `not_applicable`.
  - 3г. LLM не ответила или вернула плохой JSON → понятная ошибка «Не удалось сформулировать вопрос, попробуйте ещё раз», реплика эксперта сохраняется.
- Результат: сообщения и состояние сохранены, покрытие процессов обновлено.

**UC-16 Проверить карточку**
- Предусловие: есть черновики по передаче, пользователь — её эксперт.
- Основной поток: эксперт открывает черновик, видит слева редактор, справа источники (цитаты в контексте или видео с нужной секунды), подтверждает.
- Альтернативы: правит и подтверждает (новая ревизия, флаг `edited`); отклоняет с причиной; объединяет с другой карточкой (источники переносятся, черновик архивируется с причиной `merged`).
- Результат: подтверждённая карточка индексируется (UC-42). Если карточка была ответом на пробел, пробел закрывается и преемник получает уведомление (UC-25).

**UC-20 Задать вопрос**
- Предусловие: пользователь — преемник (или руководитель) передачи.
- Основной поток: поиск → источники → ответ с цитатами → проверка обоснованности → ответ с пометкой «все утверждения подтверждены».
- Альтернативы:
  - Релевантных источников нет → отказ без вызова LLM, создаётся пробел.
  - LLM ответила `NO_ANSWER` → отказ, создаётся пробел.
  - Часть утверждений не подтвердилась → они удаляются, ответ помечается «часть ответа удалена».
  - После удаления ничего не осталось → отказ, создаётся пробел.
- Результат: запись в `qa_logs`, события для метрик.

**UC-18 Удалить свои данные**
- Основной поток: эксперт подтверждает удаление → удаляются файлы, сообщения интервью, транскрипты, шаги → карточки без единого источника архивируются и убираются из индекса → запись в аудит.
- Результат: в базе нет сырых данных эксперта по этой передаче. Карточки, у которых остались другие источники, сохраняются.

---

## 3. Компоненты и модули

### 3.1 Развёртывание (docker compose)

```
┌──────────────────────────────── Браузер ────────────────────────────────┐
│ React SPA: вход · передачи · интервью · запись экрана · проверка ·      │
│ ассистент · база знаний · пробелы · панель · приватность                │
└──────────────┬──────────────────────────────────────────────────────────┘
               │ HTTPS, REST/JSON, JWT в httpOnly cookie
┌──────────────▼──────────────┐
│ frontend: nginx :3000       │  статика + прокси /api → backend
└──────────────┬──────────────┘
┌──────────────▼──────────────────────────┐      ┌──────────────────────────┐
│ backend: FastAPI :8000 (app.main)       │      │ db: PostgreSQL 16        │
│  routers → services → domain / repos    │◄────►│     + pgvector           │
│  при старте: alembic upgrade head       │      │  данные, индексы, jobs   │
└──────┬───────────────────┬──────────────┘      └────────────▲─────────────┘
       │ providers         │ /data (volume appdata)            │
       │                   ▼                                   │
       │            ┌──────────────┐     ┌─────────────────────┴─────────┐
       │            │ файлы:       │◄───►│ worker (python -m app.worker) │
       │            │ видео, аудио,│     │  цикл задач (SKIP LOCKED)     │
       │            │ скриншоты    │     │  ffmpeg · ASR · OCR · ПДн     │
       │            └──────────────┘     └──────────────┬────────────────┘
       │                                                │ providers
       ▼                                                ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Модели (OpenAI-совместимый HTTP):                                      │
│  профиль local-llm: vLLM / Ollama — LLM и эмбеддинги в контуре         │
│  без профиля: внешний LLM_BASE_URL (только демо-данные) / GigaChat     │
└────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Модули и правило зависимостей

```
 Уровень 3 — сценарии   ┌───────────┐ ┌────────────┐ ┌───────────┐ ┌──────┐ ┌───────────┐
                        │ interview │ │ recordings │ │ assistant │ │ gaps │ │ analytics │
                        └─────┬─────┘ └─────┬──────┘ └─────┬─────┘ └──┬───┘ └─────┬─────┘
                              │ SourceDoc   │ SourceDoc    │          │ черновик  │ только
                              ▼             ▼              ▼          ▼  карточки │ чтение
 Уровень 2 — знания     ┌───────────────────────────┐  ┌────────┐                 │
                        │        knowledge          │◄─┤ search │                 │
                        │ карточки · источники ·    │  │ чанки, │                 │
                        │ извлечение · проверка     │  │ поиск  │                 │
                        └─────────────┬─────────────┘  └────────┘                 │
                                      ▼                                           │
 Уровень 1 — контекст   ┌──────────────────────────┐  ┌───────────────────────┐   │
                        │ handovers (+ access)     │  │ privacy               │   │
                        │ передачи, участники,     │  │ согласия, удаление,   │   │
                        │ проверка прав            │  │ сроки хранения        │   │
                        └─────────────┬────────────┘  └───────────┬───────────┘   │
                                      ▼                           ▼               │
 Уровень 0 — основа     ┌──────────────────────────┐  ┌───────────────────────┐   │
                        │ org: подразделения,      │  │ identity: пользователи│   │
                        │ процессы, знающие        │  │ вход, роли            │   │
                        └──────────────────────────┘  └───────────────────────┘   │
                                                                                  │
 Платформа: core (config · db · errors · events · jobs · storage · prompts · http · logging)
            providers (llm · embeddings · asr · ocr · vlm)                ◄───────┘ все модули
 Сквозной:  audit (пишут все, через core.events)
```

Правила:
- Модуль импортирует модули **только своего уровня или ниже** и только через публичный API модуля (`modules/<name>/__init__.py`: функции сервиса и DTO). Чужие `repo.py` и `models.py` не импортируются.
- Связь **вверх** идёт через события (`core.events`) или реестры интерфейсов (раздел 5):
  - `knowledge` не знает про интервью и записи: источники он получает через `SourceResolver`, который регистрирует каждый модуль-источник;
  - `privacy` не знает, что именно удалять: каждый модуль регистрирует свой `DataEraser`;
  - `assistant` не создаёт пробел сам: он публикует `AnswerRefused`, а `gaps` на это событие подписан.
- `analytics` только читает (SQL-запросы для панели) и подписан на события для таблицы `events`.
- Внешние ключи между таблицами разных модулей есть, ORM-связей (`relationship`) между модулями нет: только id.
- Правила можно проверять автоматически через `import-linter` в CI (по желанию, ~20 строк конфигурации).

### 3.3 Устройство модуля

```
modules/interview/
├── __init__.py      # публичный API: что можно импортировать другим модулям
├── router.py        # HTTP-эндпоинты
├── schemas.py       # Pydantic DTO запросов и ответов
├── service.py       # сценарии: start, post_message, finish …
├── repo.py          # запросы SQLAlchemy
├── models.py        # ORM-модели таблиц модуля
├── handlers.py      # подписки на события и обработчики задач worker
└── domain/          # чистая логика без ввода-вывода
    ├── aspects.py
    ├── state.py
    └── planner.py
```

Маленькому модулю (например, `audit`) отдельные файлы не нужны: всё может лежать в одном-двух.

### 3.4 Обязанности модулей

| Модуль | Таблицы | Что делает |
|---|---|---|
| `identity` | users | вход, JWT, хеши паролей, текущий пользователь, CRUD пользователей (админ) |
| `org` | org_units, processes, process_holders | подразделения, процессы, кто знает процесс («фактор автобуса») |
| `handovers` | handovers, handover_members, handover_processes | передачи дел, участники и их роли, **единая проверка прав** (`access.py`) |
| `privacy` | consents | текст и версия согласия, принятие и отзыв, проверка `require_consent`, каскад удаления через реестр `DataEraser`, чистка по сроку |
| `interview` | interview_sessions, interview_messages, process_aspects | фазы, анализ хода, планировщик, генерация вопроса, голос, активное время; отдаёт `SourceDocument` для извлечения |
| `recordings` | recordings, transcript_segments, recording_steps | загрузка, ffmpeg, ASR, разбиение на шаги, скриншоты, размытие ПДн, черновик инструкции |
| `knowledge` | knowledge_cards, card_revisions, card_sources | извлечение из любого `SourceDocument`, валидация цитат, дедупликация, проверка экспертом, ревизии, база знаний |
| `search` | card_chunks | разбиение на чанки, эмбеддинги, гибридный поиск (вектор + полнотекст + RRF) |
| `assistant` | qa_logs | ответ по источникам, проверка обоснованности, решение об отказе, обратная связь |
| `gaps` | gaps | очередь пробелов, ответ → черновик карточки, закрытие после подтверждения, уведомления |
| `analytics` | events | продуктовые события, метрики, CSV, покрытие подтверждёнными карточками, риск |
| `audit` | audit_log | журнал значимых действий |
| `core.jobs` | jobs | очередь задач, повторы, идемпотентность |
| `core.storage` | assets | сохранение и стриминг файлов (Range), sha256, проверка MIME |

---

## 4. Модель данных (диаграмма классов)

Во всех таблицах: `id UUID`, `created_at`, `updated_at`. Связи: `1──*` один-ко-многим, `0..1` необязательная.
Изменения относительно ТЗ помечены `[+]` и описаны в разделе 9.

```
┌──────────────┐ 1      * ┌──────────────────────┐ *      1 ┌───────────────────────────┐
│ User         │──────────│ HandoverMember [+]   │──────────│ Handover                  │
│ email        │          │ role: expert |       │          │ org_unit_id, manager_id   │
│ full_name    │          │  successor | manager │          │ reason, deadline          │
│ role(global) │          └──────────────────────┘          │ status                    │
│ password_hash│                                            └──┬──────┬──────┬──────┬───┘
└──────┬───────┘                                               │1     │1     │1     │1
       │1                                                      │      │      │      │
       │*        ┌──────────────┐ 1    * ┌──────────────┐      │      │      │      │
┌──────┴───────┐ │ OrgUnit      │────────│ Process      │◄─────┼──────┘      │      │
│ProcessHolder │ │ name         │        │ name, freq,  │ *  * │ HandoverProcess    │
│ level: owner │─┤              │        │ criticality  │      │                    │
│ |knows|learn.│ └──────────────┘        └──────┬───────┘      │                    │
└──────────────┘ (process_id, user_id)          │1             │*                   │*
                                                │*      ┌──────┴──────────┐  ┌──────┴──────┐
                                 ┌──────────────┴─────┐ │ Consent         │  │ QaLog       │
                                 │ ProcessAspect [+]  │ │ user_id         │  │ question    │
                                 │ handover_id        │ │ text_version    │  │ answer      │
                                 │ aspect, status     │ │ text_hash       │  │ status      │
                                 │ not_applicable     │ │ accepted_at     │  │ groundedness│
                                 └────────────────────┘ │ revoked_at      │  │ retrieval   │
                                                        └─────────────────┘  │ prompt_ver.[+]
                                                                             └──────┬──────┘
 Handover 1──* InterviewSession                                                     │0..1
┌───────────────────────┐ 1   * ┌──────────────────────┐ 0..1   1 ┌──────────┐      │
│ InterviewSession      │───────│ InterviewMessage     │──────────│ Asset    │      │
│ status, phase         │       │ seq, role, content   │  audio   │ kind     │      │
│ state_json(versioned) │       │ meta(aspect, probe)  │          │ path,mime│      │
│ active_seconds        │       └──────────────────────┘          │ sha256   │      │
└───────────────────────┘                                         │ deleted_at      │
                                                                  └────▲─────┘      │
 Handover 1──* Recording                                    video 1    │ 0..1 image │
┌───────────────────────┐ 1   * ┌──────────────────────┐               │            │
│ Recording             │───────│ TranscriptSegment    │               │            │
│ title, status, error  │───┐   │ start_ms,end_ms,text │               │            │
│ video_asset_id ───────┼───┼───┴──────────────────────┘               │            │
└───────────────────────┘   │ * ┌──────────────────────┐               │            │
                            └───│ RecordingStep        │───────────────┘            │
                                │ idx,title,action     │ screenshot_asset_id        │
                                │ start_ms,end_ms      │                            │
                                │ screenshot_blurred   │                            │
                                └──────────────────────┘                            │
 Handover 1──* KnowledgeCard                                                        │
┌───────────────────────┐ 1   * ┌──────────────────────────────────────┐            │
│ KnowledgeCard         │───────│ CardSource                           │            │
│ type, title, summary  │       │ source_type: interview_message |     │            │
│ body_md, applies_when │       │   transcript_segment | recording_step│            │
│ process_id 0..1       │       │   | gap_answer [+]                   │            │
│ status, version       │       │ source_id ──► (полиморфная ссылка)   │            │
│ origin                │       │ quote, start_ms, end_ms              │            │
│ duplicate_of 0..1 [+] │       └──────────────────────────────────────┘            │
│ approved_by/at        │ 1   * ┌──────────────────────┐                            │
│ review_seconds        │───────│ CardRevision [+]     │  снимок до правки          │
│                       │       │ version, поля, автор │                            │
│                       │ 1   * ┌──────────────────────┐                            │
│                       │───────│ CardChunk            │  только approved           │
└───────────▲───────────┘       │ text, embedding(1024)│                            │
            │ answered_card     │ tsv, handover_id [+] │                            │
            │ 0..1              │ embedding_model [+]  │                            │
┌───────────┴───────────┐       └──────────────────────┘                            │
│ Gap                   │◄──────────────────────────────────────────────────────────┘
│ question, status      │  qa_log_id 0..1
│ assignee_id [+]       │
│ answer_text [+]       │
│ answered_by/at        │
└───────────────────────┘

 Служебные: AuditLog(user_id, action, entity, entity_id, meta, at)
            Job(type, payload, status, attempts, dedup_key [+] unique, run_after, error)
            Event(user_id, handover_id, name, props, at)
```

---

## 5. Ключевые интерфейсы (точки расширения)

### 5.1 Источники знаний

Это главная абстракция, ради которой стоит потратить время в M0. Извлечение, валидация цитат, экран проверки и ссылки ассистента работают с **источником вообще**, а не с интервью или записью. Новый вид источника (например, загрузка регламентов в PDF) добавляется новым модулем без правок в `knowledge`.

```python
class SourceType(StrEnum):
    INTERVIEW_MESSAGE = "interview_message"
    TRANSCRIPT_SEGMENT = "transcript_segment"
    RECORDING_STEP = "recording_step"
    GAP_ANSWER = "gap_answer"

@dataclass(frozen=True)
class SourceRef:
    type: SourceType
    id: UUID

@dataclass(frozen=True)
class SourceFragment:              # кусок текста, на который может ссылаться цитата
    ref: SourceRef
    text: str
    label: str                     # «Реплика 12», «03:15–03:40»
    start_ms: int | None = None
    end_ms: int | None = None

@dataclass(frozen=True)
class SourceDocument:              # вход для извлечения карточек
    handover_id: UUID
    origin: CardOrigin             # interview | recording | gap_answer
    fragments: list[SourceFragment]
    context: dict[UUID, str]       # например, вопрос интервьюера перед репликой; доказательством не считается

class SourceResolver(Protocol):    # регистрирует каждый модуль-источник
    source_type: SourceType
    async def resolve(self, db: AsyncSession, ids: list[UUID], viewer: Viewer) -> dict[UUID, SourceView]: ...
    # SourceView: текст с контекстом, ссылка на медиа и таймкод, видимость для роли
```

### 5.2 Удаление данных

```python
class DataEraser(Protocol):        # регистрирует каждый модуль, который хранит данные сотрудника
    async def erase(self, db: AsyncSession, *, user_id: UUID, handover_id: UUID) -> list[SourceRef]: ...

# privacy.service.erase_my_data():
#   refs = [ref for e in registry for ref in await e.erase(...)]
#   await knowledge.on_sources_deleted(db, refs)   # архивирует карточки без источников
#   audit(...)
```

### 5.3 События и задачи

```python
@dataclass(frozen=True)
class CardApproved(Event):
    card_id: UUID
    version: int
    origin: CardOrigin
    edited: bool

# Синхронный подписчик: выполняется в той же транзакции (дешёвые действия)
bus.subscribe(CardApproved, gaps.handlers.close_gap_if_answer)
bus.subscribe(CardApproved, analytics.handlers.record_event)

# Подписчик-задача: в той же транзакции в таблицу jobs пишется строка, worker выполнит её позже
bus.subscribe_job(CardApproved, "index_card", dedup_key=lambda e: f"index_card:{e.card_id}:{e.version}")

await bus.publish(db, CardApproved(...))
```

Список событий для MVP:

| Событие | Кто публикует | Кто подписан |
|---|---|---|
| `InterviewTurnCompleted` | interview | analytics |
| `InterviewSessionFinished` | interview | job `extract_cards`, analytics |
| `RecordingUploaded` | recordings | job `process_recording`, analytics |
| `RecordingProcessed` | recordings | analytics |
| `CardDrafted` / `CardDropped` | knowledge | analytics |
| `CardApproved` | knowledge | job `index_card`, gaps, analytics, audit |
| `CardRejected` / `CardArchived` | knowledge | job `unindex_card`, analytics, audit |
| `AnswerShown` | assistant | analytics |
| `AnswerRefused` | assistant | gaps (создать пробел), analytics |
| `GapAnswered` | gaps | analytics |
| `ConsentAccepted` / `ConsentRevoked` | privacy | audit |
| `DataErased` | privacy | audit |

Задачи worker идемпотентны: `dedup_key` уникален среди незавершённых задач, обработчик можно безопасно выполнить повторно. Повтор до 3 раз с экспоненциальной задержкой.

### 5.4 Провайдеры

Интерфейсы — как в разделе 5.1 ТЗ. Добавление: у эмбеддингов, кроме `sentence_transformers` и `fake`, есть реализация `openai_compatible` (раздел 9, пункт 7).

```python
# providers/registry.py — единственное место, где конфиг превращается в реализации
def build_providers(settings: Settings) -> Providers: ...
# FastAPI: Depends(get_providers); worker: создаётся один раз при старте
```

Все HTTP-вызовы провайдеров идут через `core.http.client()`. При `OFFLINE_MODE=true` он запрещает нелокальные адреса.

### 5.5 Промпты

```python
prompt = prompts.render("analyze_turn", processes=..., question=..., answer=...)
# prompt.messages, prompt.name, prompt.version  (версия — из front matter файла)
result = await llm.complete_json(prompt.messages, TurnAnalysis)
```

### 5.6 Доступ

```python
# handovers/access.py — единая политика
class HandoverRole(StrEnum): ADMIN, MANAGER, EXPERT, SUCCESSOR

async def get_handover_role(db, user, handover_id) -> HandoverRole | None: ...
def require_handover_access(*allowed: HandoverRole) -> Depends: ...   # 403 с текстом на русском

# Видимость карточек — один фильтр, который используют все запросы knowledge и search:
def visible_card_statuses(role: HandoverRole) -> set[CardStatus]: ...  # преемник → {approved}
```

### 5.7 Поиск

```python
class Retriever(Protocol):
    async def search(self, db, query: str, scope: SearchScope, k: int) -> list[ScoredChunk]: ...
# HybridRetriever = VectorRetriever + FullTextRetriever + rrf() из search/domain
```

Ассистент зависит только от `Retriever`. Если поиск нужно поменять (другой реранкер, другой индекс), меняется только модуль `search`.

---

## 6. Диаграммы последовательности

### 6.1 Ход интервью (UC-11)

```
Эксперт    router        InterviewService      LLM          domain           БД
   │ POST /interviews/{id}/messages │             │              │              │
   │──────────►│ access + consent   │             │              │              │
   │           │───────────────────►│ сохранить реплику эксперта ──────────────►│
   │           │                    │ analyze_turn│              │              │
   │           │                    │────────────►│              │              │
   │           │                    │◄─ TurnAnalysis (JSON)      │              │
   │           │                    │ apply_analysis(state, a) ─►│ новое state  │
   │           │                    │ plan_next(state) ─────────►│ NextStep     │
   │           │                    │◄───────────────────────────│ (цель, аспект, тип зонда)
   │           │                    │ generate_question           │              │
   │           │                    │────────────►│              │              │
   │           │                    │◄─ текст вопроса            │              │
   │           │                    │ сохранить вопрос, state, process_aspects, │
   │           │                    │ событие InterviewTurnCompleted ──────────►│
   │◄──────────│◄── {question, coverage}                                        │
```

### 6.2 Извлечение карточек (UC-40)

```
InterviewService.finish()
   └─ publish InterviewSessionFinished ──(та же транзакция)──► jobs: extract_cards(session_id)

worker ─► handler extract_cards
   1. interview.build_source_document(session_id) → SourceDocument (реплики эксперта + вопросы как контекст)
   2. knowledge.extract(doc):
        windows(doc, ~3000 токенов, перекрытие 1 реплика)         [domain]
        для каждого окна: LLM extract_cards → кандидаты (JSON)
        validate_quotes(кандидат, fragments)                       [domain]
            → сохраняется найденный фрагмент ИСТОЧНИКА, а не текст от LLM
        нет валидных цитат → CardDropped (событие)
        match_process(process_name, процессы передачи)             [domain, rapidfuzz]
        embed(title + summary) → find_duplicate(≥ 0.9)             [domain]
            дубль-черновик → добавить источники;  иначе → новый draft (duplicate_of)
        сохранить KnowledgeCard(draft) + CardSource → CardDrafted
```

### 6.3 Проверка и индексация (UC-16, UC-42)

```
Эксперт ─► POST /cards/{id}/approve {правки?}
   KnowledgeService:
     если есть правки → CardRevision(снимок старой версии), version += 1
     status = approved, approved_by/at, review_seconds
     publish CardApproved(card_id, version, origin, edited)
       ├─ (sync)  analytics: событие card_approved
       ├─ (sync)  audit
       ├─ (sync)  gaps: если origin = gap_answer → gap.answered, уведомление преемнику
       └─ (job)   index_card(card_id, version):
                    chunk(body_md) [domain] → embed → удалить старые чанки → вставить новые
```

### 6.4 Вопрос ассистенту (UC-20)

```
Преемник ─► POST /assistant/ask {handover_id, question}
  AssistantService:
   1. retriever.search(q, scope=handover)
        вектор top-20 ┐
        FTS   top-20  ┴─► rrf(k=60) → top-8 чанков → ≤ 5 карточек               [domain]
   2. should_refuse(best_cosine, fts_hits, threshold) ── да ──┐                   [domain]
   3. LLM answer.md → текст | NO_ANSWER ────────── NO_ANSWER ─┤
   4. split_claims(текст) → LLM verify_claims (пакетом ≤ 8)                       [domain]
   5. assemble(claims, supported) → итоговый ответ | пусто ── пусто ──┤           [domain]
   6. QaLog(answered | partial, groundedness, retrieval, prompt_version)
      publish AnswerShown                                             │
                                                                      ▼
                                       QaLog(refused) + publish AnswerRefused
                                                └─► gaps: создать Gap(open, assignee = эксперт)
  ◄── {status, answer, citations[{n, card_id, title, type}], groundedness, qa_id}
```

### 6.5 Обработка записи экрана (UC-15, UC-41)

```
POST /recordings (multipart) → проверка MIME/размера → storage.save → Asset + Recording(uploaded)
   └─ publish RecordingUploaded ──► jobs: process_recording(recording_id)

worker:
  status = processing
  ffmpeg → wav 16 кГц моно, длительность
  ASR → TranscriptSegment[]
  LLM segment_recording → шаги → fix_steps(длительность)          [domain: обрезка, сортировка]
  для каждого шага: ffmpeg кадр (end_ms − 500) → OCR → detect_pii [domain] → blur → Asset(image)
  (VLM_ENABLED) уточнить описание шага
  SourceDocument(fragments = шаги) → knowledge.create_procedure_draft(...)
  status = ready → RecordingProcessed          (ошибка → status = failed, error)
```

### 6.6 Удаление своих данных (UC-18)

```
Эксперт ─► DELETE /privacy/my-data?handover_id=
  PrivacyService.erase():
    для каждого DataEraser:
       interview  → удалить сообщения, аудио-assets (файлы физически)  → SourceRef[]
       recordings → удалить записи, сегменты, шаги, видео и скриншоты  → SourceRef[]
       gaps       → удалить тексты ответов эксперта                    → SourceRef[]
    knowledge.on_sources_deleted(refs):
       удалить CardSource по refs
       карточки без источников → archived(source_deleted) → CardArchived → unindex_card
    audit: DataErased
```

---

## 7. Диаграммы состояний

```
Передача дел
  draft ──активировать──► active ──завершить (руководитель)──► completed
    └──────────────┬─────────┘
                   └──отменить──► cancelled

Сессия интервью (status)                 Фазы (phase)
  active ◄──продолжить── paused            intro → map → ┌► walkthrough → deepen ┐ → wrapup
    │  └──пауза──────────►                               └──── следующий процесс ◄┘
    └──завершить──► finished               (покрытие ≥ 70% или кнопка «Следующий процесс»)

Карточка знаний
            ┌──────── правка подтверждённой (version+1) ────────┐
            ▼                                                   │
  draft ──подтвердить──► approved ─────────────────────────────┘
    │                       │
    ├──отклонить──► rejected│
    │                       └──все источники удалены──► archived(source_deleted)
    ├──объединить──► archived(merged)
    └──все источники удалены──► archived(source_deleted)

Пробел
  open ──эксперт ответил──► open + answered_card_id (в UI «ответ на проверке»)
    │                              └──карточку подтвердили──► answered
    └──закрыть (руководитель)──► dismissed

Запись экрана                       Задача (jobs)
  uploaded → processing → ready       queued → running → done
                     └──► failed               └─ ошибка, attempts < 3 → queued (run_after = backoff)
                                               └─ ошибка, attempts = 3 → failed
```

---

## 8. Структура репозитория

```
successor/
├── CLAUDE.md                        # правила для агента + ссылка на docs/SPEC.md
├── README.md                        # запуск, демо-учётки
├── Makefile                         # up, down, test, lint, seed-demo, eval, gen-api, migrate
├── docker-compose.yml               # db, backend, worker, frontend; профиль local-llm
├── .env.example
├── .github/workflows/ci.yml         # lint + тесты (fake-провайдеры, postgres в services) + eval --provider fake
│
├── docs/
│   ├── SPEC.md                      # ТЗ
│   ├── architecture.md              # этот документ
│   ├── decisions.md                 # журнал решений
│   └── privacy.md                   # M4
│
├── backend/
│   ├── pyproject.toml               # uv; ruff, mypy, pytest, import-linter
│   ├── Dockerfile                   # один образ для backend и worker (+ ffmpeg)
│   ├── alembic.ini
│   ├── alembic/
│   │   ├── env.py
│   │   └── versions/
│   ├── app/
│   │   ├── main.py                  # create_app(): роутеры, обработчики ошибок, middleware
│   │   ├── worker/
│   │   │   └── __main__.py          # python -m app.worker: цикл задач
│   │   ├── core/
│   │   │   ├── config.py            # pydantic-settings; все пороги здесь
│   │   │   ├── db.py                # engine, session, Base, миксины UUID/timestamps
│   │   │   ├── security.py          # argon2, JWT, cookie
│   │   │   ├── deps.py              # current_user, db, providers
│   │   │   ├── errors.py            # AppError(code, detail на русском) → {"detail", "code"}
│   │   │   ├── events.py            # шина событий: subscribe / subscribe_job / publish
│   │   │   ├── jobs.py              # модель Job, enqueue, реестр обработчиков, цикл, backoff
│   │   │   ├── storage.py           # Storage (LocalStorage), Asset, стриминг с Range, MIME
│   │   │   ├── prompts.py           # загрузка *.md, front matter (version), Jinja2
│   │   │   ├── http.py              # httpx-клиент с проверкой OFFLINE_MODE
│   │   │   ├── health.py            # /api/health
│   │   │   └── logging.py           # без текстов пользователей в логах
│   │   ├── providers/
│   │   │   ├── registry.py          # build_providers(settings)
│   │   │   ├── llm/                 # base.py, openai_compatible.py, gigachat.py, fake.py, structured.py
│   │   │   ├── embeddings/          # base.py, sentence_transformers.py, openai_compatible.py, fake.py
│   │   │   ├── asr/                 # base.py, faster_whisper.py, gigaam.py, fake.py
│   │   │   ├── ocr/                 # base.py, easyocr.py, tesseract.py, fake.py
│   │   │   └── vlm/                 # base.py, openai_compatible.py, fake.py
│   │   ├── modules/
│   │   │   ├── identity/            # models, schemas, repo, service, router
│   │   │   ├── org/                 # + domain/matching.py (нечёткое сравнение названий процессов)
│   │   │   ├── handovers/           # + access.py
│   │   │   ├── privacy/             # + erasure.py (реестр DataEraser), retention.py, consent_text
│   │   │   ├── interview/
│   │   │   │   ├── domain/          # aspects.py, state.py, analysis.py, planner.py, timing.py, fallback.py
│   │   │   │   ├── llm.py           # analyze_turn и генерация вопроса (LLM)
│   │   │   │   ├── sources.py       # SourceResolver, build_source_document (DataEraser — M4)
│   │   │   │   └── models, schemas, repo, service, router, handlers
│   │   │   ├── recordings/
│   │   │   │   ├── domain/          # steps.py (валидация интервалов)
│   │   │   │   ├── pii/             # detectors.py (регулярки, Луна, natasha), blur.py
│   │   │   │   ├── media.py         # ffmpeg: аудио, кадры, длительность
│   │   │   │   ├── pipeline.py      # process_recording
│   │   │   │   ├── sources.py
│   │   │   │   └── models, schemas, repo, service, router, handlers
│   │   │   ├── knowledge/
│   │   │   │   ├── domain/          # sources.py (SourceRef/Fragment/Document), card_types.py,
│   │   │   │   │                    # quotes.py, windows.py, dedup.py
│   │   │   │   ├── extraction.py    # extract(SourceDocument)
│   │   │   │   ├── resolvers.py     # реестр SourceResolver
│   │   │   │   └── models, schemas, repo, service, router, handlers
│   │   │   ├── search/
│   │   │   │   ├── domain/          # chunking.py, rrf.py
│   │   │   │   ├── retriever.py     # Vector/FullText/Hybrid
│   │   │   │   ├── indexer.py
│   │   │   │   └── models, repo, handlers
│   │   │   ├── assistant/
│   │   │   │   ├── domain/          # claims.py (разбиение, сборка), refusal.py
│   │   │   │   ├── answerer.py
│   │   │   │   ├── verifier.py
│   │   │   │   └── models, schemas, repo, service, router, handlers
│   │   │   ├── gaps/                # models, schemas, repo, service, router, handlers, sources.py
│   │   │   ├── analytics/
│   │   │   │   ├── domain/          # risk.py, coverage.py (по подтверждённым карточкам)
│   │   │   │   ├── metrics.py       # SQL-агрегаты, CSV
│   │   │   │   └── models, schemas, router, handlers
│   │   │   └── audit/               # models, service, router, handlers
│   │   └── prompts/                 # interviewer_system.md, analyze_turn.md, extract_cards.md,
│   │                                # segment_recording.md, answer.md, verify_claims.md, consent_v1.md
│   └── tests/
│       ├── conftest.py              # fake-провайдеры, БД, фабрики
│       ├── unit/                    # повторяет modules/*/domain — без БД и сети
│       ├── integration/             # Postgres + pgvector, сквозные сценарии
│       └── fixtures/                # llm/*.json, images/, audio/*.transcript.json
│
├── frontend/
│   ├── package.json, vite.config.ts, tsconfig.json, tailwind.config.ts
│   ├── Dockerfile, nginx.conf
│   └── src/
│       ├── app/                     # роутер, layout, охрана маршрутов по ролям, баннер «Демо-режим»
│       ├── api/                     # schema.d.ts (генерируется), client.ts, хуки TanStack Query
│       ├── features/                # auth, handovers, consent, interview, recordings, review,
│       │                            # assistant, knowledge, gaps, dashboard, privacy
│       ├── components/              # ui/ (shadcn) + общие (StatusBadge, EmptyState, VideoAtTime)
│       └── lib/
│
├── eval/
│   ├── datasets/                    # demo_qa.jsonl, demo_extraction_gold.json
│   ├── run_eval.py                  # вызывает сервисы app напрямую (без HTTP), --provider fake|real
│   ├── judge.py
│   └── reports/
│
├── seed/
│   ├── data/                        # yaml/json: пользователи, процессы, сценарий интервью, карточки
│   └── seed.py                      # make seed-demo; идемпотентный
│
└── demo/
    └── mock-portal/                 # статический «Учебный портал (демо)»
```

---

## 9. Отклонения от ТЗ и открытые вопросы

### 9.1 Предлагаемые отклонения (нужно согласие)

| # | Что | В ТЗ | Предложение | Зачем |
|---|---|---|---|---|
| 1 | Структура backend | по слоям: `api/`, `schemas/`, `services/`, `db/` | по модулям: `modules/<область>/{router,service,domain,…}` | правка одной функции затрагивает одну папку; проще распределить работу в команде и не мешать друг другу |
| 2 | Участники передачи | `handovers.expert_id`, `successor_id` | таблица `handover_members(handover_id, user_id, role)` | несколько преемников или экспертов, переназначение пробела другому эксперту (п. 7.8 ТЗ) без миграции схемы |
| 3 | Покрытие аспектов | внутри `interview_sessions.state_json` | таблица `process_aspects(handover_id, process_id, aspect, status, not_applicable)` | панели и тепловой матрице не нужно разбирать JSON сессий; несколько сессий пишут в одно место |
| 4 | Ревизии карточек | только `version int` | таблица `card_revisions` (снимок до правки) | «Подтвердить с правками» сохраняет историю; метрика «доля с правками» и откат |
| 5 | Источник-ответ на пробел | `source_type` без `gap_answer` | добавить `gap_answer` (+ `gaps.answer_text`) | ТЗ требует, чтобы ответ на пробел был источником карточки, а тип для него не предусмотрен |
| 6 | Индекс | `card_chunks(card_id, text, embedding, tsv)` | + `handover_id`, `org_unit_id`, `process_id`, `embedding_model` | фильтр без JOIN; при смене модели эмбеддингов видно, что нужно переиндексировать |
| 7 | Эмбеддинги | только `sentence_transformers` в процессе | + провайдер `openai_compatible` (bge-m3 через Ollama/TEI) | модель ~2 ГБ иначе грузится и в backend, и в worker; образы легче, локальный контур не меняется |
| 8 | Очередь | — | `jobs.dedup_key` (уникальный для незавершённых) | идемпотентность задач, требование раздела 16 |
| 9 | Логи ассистента | — | `qa_logs.prompt_version`, `model` | сравнение eval-прогонов и ответов между версиями промптов |
| 10 | Дубли | пометка «возможный дубль: <id>» | поле `knowledge_cards.duplicate_of` | кнопку «Объединить» можно показать без разбора текста |

### 9.2 Решённые вопросы

1. Фронтенд — React + TypeScript (D-011).
2. Ответ ассистента без SSE-стриминга в MVP, целиком после проверки (D-012).
3. SQLAlchemy async, тяжёлые шаги через `asyncio.to_thread` (D-013).
4. `import-linter` в CI с M0 (D-014).
5. Правило для агента: простой вариант + запись решения; архитектура и стек — через команду (D-015).

---

## 10. Как вносить типовые изменения

| Изменение | Что трогаем |
|---|---|
| Новая LLM или другой сервер моделей | `providers/llm/<new>.py` + строка в `registry.py` + `.env` |
| Другая модель эмбеддингов | `.env`; при другой размерности — миграция `card_chunks.embedding` + переиндексация (видно по `embedding_model`) |
| Новый вид источника (документы, почта, чат) | новый модуль: `SourceDocument` + `SourceResolver` + `DataEraser`; извлечение и проверка не меняются |
| Новый тип карточки | `knowledge/domain/card_types.py` (подпись, связь с аспектами) + промпт `extract_cards.md` |
| Другие аспекты или методика интервью | `interview/domain/aspects.py` (данные), порядок приоритета в `planner.py`, промпты |
| Другая формула риска или пороги | `analytics/domain/risk.py` + `core/config.py` |
| Другой поиск (реранкер, другой индекс) | `search/` за интерфейсом `Retriever` |
| S3/MinIO вместо диска | `core/storage.py` — новая реализация `Storage` |
| SSO/AD | `identity/` — новый способ входа, остальное работает через `current_user` |
| Новая метрика | подписка в `analytics/handlers.py` + запрос в `metrics.py` |
| Новая роль или правило доступа | `handovers/access.py` — одно место |
