# Digital Mechanic — ИИ-агент для диагностики ДВС

Проект хакатона «ИИкузница / НейроДВС»: механик выбирает машину из парка,
запускает акустическую проверку, ИИ-агент объясняет результат по заводским
руководствам (RAG, с цитатами `[doc_id, стр. N]` и панелью документа) и
оформляет заявку на дефектовку в систему ТОиР.

**Стек:** FastAPI + агентный цикл на tool calling (OpenAI / Anthropic / Gemini,
SSE-стриминг шагов агента) · Vue 3 + TypeScript (тёмная тема) · SQLite ·
комплектные mock-интеграции ML-диагностики и ТОиР.

Все данные в системе синтетические; на экране входа требуется отметить
согласие на обработку данных (152-ФЗ).

---

## Запуск за 5 минут

### 0. Что нужно

- Python **3.11+**
- Node.js **18+** (сборка фронтенда)
- Доступ к любой LLM: локальной OpenAI-совместимой (vLLM, llama.cpp, Ollama…)
  или облачной (Anthropic / Gemini тоже поддерживаются)

### 1. Клонировать и установить

```bash
git clone https://github.com/Mistress-Lukutar/digital-mechanic
cd digital-mechanic

python -m venv .venv
.venv\Scripts\pip install -e ".[dev]"     # Windows
# .venv/bin/pip install -e ".[dev]"       # Linux/macOS

cd frontend && npm install && cd ..
```

### 2. Настроить .env

```bash
copy .env.example .env     # Windows
cp .env.example .env       # Linux/macOS
```

Минимум, который стоит вписать, — параметры LLM:

```
LLM_PROTOCOL=openai_compatible
LLM_BASE_URL=http://<хост>:<порт>/v1
LLM_API_KEY=sk-...
LLM_MODEL=<имя модели>
```

URL заглушек (8001/8002), RAG (8003) и каталог мануалов уже предзаполнены.

### 3. Запустить одной командой

```bat
scripts\start.bat     :: Windows
scripts/start.sh      :: Linux/macOS
```

Скрипт при первом запуске сам соберёт фронтенд в `static/dist`, поднимет
заглушки ML (:8001) и ТОиР (:8002) и запустит API вместе с UI на
**http://localhost:8011** (проверка живости: `/health`).

### 4. Войти

- При пустой базе на старте создаётся администратор, пароль печатается
  **в консоль API-процесса**; после первого входа обязательна смена пароля.
- **Админ:** дашборд экономики (usage, стоимость запросов), управление
  пользователями, настройки LLM (провайдер/модель/ключ) прямо в UI.
- Создайте через админку пользователя-механика и работайте под ним:
  гараж → чат с агентом → заявка. Механику также доступны график
  `anomaly_score` и сводка «Главный механик» по всему парку.

Без доступной LLM чат не отвечает, но диагностика, парк и заявки работают.

## Руководства (авторские права)

Заводские PDF **не входят в репозиторий** (copyright). Чтобы включить
поиск по документации, положите шесть issued-руководств в `data/manuals/`
под именами из `data/manuals/manifest.json` — или укажите внешний,
контролируемый вами каталог через `MANUALS_DIR` в `.env`. Без мануалов
`search_manuals` честно отвечает «инструкции недоступны» (тест-кейс
«нет инструкции»), остальной сценарий полностью работает. Подробности:
[data/manuals/README.md](data/manuals/README.md).

## Режим разработки

`scripts\dev.bat` / `scripts/dev.sh` — то же, но API на **:8000** с
автоперезагрузкой и фронтенд в vite dev-сервере на **http://localhost:5173**
(прокси `/api` → 8000). Открывать именно `localhost` — vite слушает IPv6.

Ручной вариант (четыре терминала из корня):

```bash
# Заглушки (MOCK_DATA_PATH — абсолютный путь к файлу парка)
MOCK_DATA_PATH=<абс>/data/vehicles.json \
  .venv/Scripts/python.exe -m uvicorn mock_ml.app:app --port 8001 --app-dir vendor
MOCK_DATA_PATH=<абс>/data/vehicles.json \
  .venv/Scripts/python.exe -m uvicorn mock_toir.app:app --port 8002 --app-dir vendor

# API
.venv/Scripts/python.exe -m uvicorn mechanic.main:app --port 8000

# Фронтенд (прокси /api → 8000)
cd frontend && npm run dev
```

## Структура репозитория

| Путь | Содержимое |
|---|---|
| `src/mechanic/` | FastAPI-бэкенд: агентный цикл, инструменты агента, сервисы, API |
| `shared/` | Контрактные Pydantic-модели (общие с RAG-модулем участника B) |
| `frontend/` | Vue 3 + TypeScript SPA: гараж, SSE-чат с карточками, заявки, админка |
| `data/` | Комплектные синтетические данные: `vehicles.json`, `fault_types.json`; `manuals/` — манифест документов (PDF поставляются отдельно) |
| `vendor/` | Комплектные заглушки: Mock ML (`POST /diagnose`), Mock ТОиР (`POST /tickets`), OpenAPI-спеки |
| `prompts/` | Системный промпт агента (`{vehicle_block}` / `{docs_block}`) |
| `tests/` | pytest-набор бэкенда |
| `e2e/` | Playwright UI/UX-смоук: вход, навигация по всем страницам, админка, контроль ошибок консоли/сети |

## Проверки

```bash
.venv/Scripts/python.exe -m pytest tests -q
.venv/Scripts/python.exe -m ruff check src shared tests
cd frontend && npm run build    # vue-tsc strict + vite build
```

UI/UX-смоук (требует `pip install -e ".[e2e]"`; браузер — системный Edge/Chrome,
без скачивания Playwright-браузеров; стенд — свои моки + API на случайных
портах под `/mech/`, как за обратным прокси):

```bash
.venv/Scripts/python.exe -m pytest e2e -v
```

Сьюит после каждого теста проверяет, что на странице не было JS-ошибок,
ошибок консоли и ответов 4xx/5xx (кроме ожидаемых 401 на `auth/login`/`auth/me`
— семантика «не авторизован»).
