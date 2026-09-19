# website-store: High-Performance Catalog & Headless Scraping Pipeline

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15_Alpine-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)](https://postgresql.org)
[![Playwright](https://img.shields.io/badge/Playwright-Stealth-2EAD33?style=for-the-badge&logo=playwright&logoColor=white)](https://playwright.dev)
[![Telegram CDN](https://img.shields.io/badge/Storage-Telegram_CDN-2CA5E0?style=for-the-badge&logo=telegram&logoColor=white)](https://core.telegram.org/bots/api)
[![HTMX](https://img.shields.io/badge/Frontend-HTMX_1.9-3366CC?style=for-the-badge)](https://htmx.org)
[![Alpine.js](https://img.shields.io/badge/State-Alpine.js_3.14-8BC0D0?style=for-the-badge&logo=alpinedotjs&logoColor=white)](https://alpinejs.dev)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://docker.com)
[![Diátaxis](https://img.shields.io/badge/Docs-Diátaxis_Framework-00ADD8?style=for-the-badge)](https://diataxis.fr)

Высокопроизводительный маркетплейс-каталог уличной одежды и обуви со сквозным конвейером сбора данных (30 000+ альбомов / 240 000+ изображений). Система включает асинхронный краулер с обходом WAF-защиты Yupoo, распределенную очередь задач на базе блокировок PostgreSQL, бессерверное медиа-хранилище на базе Telegram Bot API и легковесную веб-витрину с нечетким триграммным поиском (`pg_trgm`).

---

## 🏗️ Архитектура системы (System Design)

Пайплайн разделен на три изолированных слоя: **Acquisition**, **Storage** и **Web Presentation**:

```mermaid
flowchart TD
    subgraph Layer1 ["1. Слой сбора данных и CDN (Acquisition Layer)"]
        Yupoo[Yupoo Supplier Catalog]
        PW["Playwright Stealth Engine<br>(Referer Inject + Jitter + Warmup)"]
        Discovery["run_discovery.py<br>(Дерево категорий)"]
        Crawler["run_crawler.py<br>(Сбор альбомов по фильтрам)"]
        Worker["run_worker.py (AlbumWorker)<br>In-Memory Streaming (io.BytesIO)"]
        TG_CDN["Telegram Bot API + Private Channel<br>(Бесплатное бессерверное хранилище)"]
    end

    subgraph Layer2 ["2. Слой персистентности и очередей (PostgreSQL 15)"]
        Queue["Атомарная очередь задач<br>FOR UPDATE SKIP LOCKED"]
        DB[(PostgreSQL 15-alpine)]
        GIN["pg_trgm GIN Index<br>(Нечеткий поиск за 3-8 мс)"]
        M2M["M2M Связи<br>(Категории ↔ Альбомы)"]
    end

    subgraph Layer3 ["3. Веб-витрина и API (FastAPI + HTMX)"]
        App["FastAPI Core (ServiceRegistry Lifespan)"]
        Cache["MediaService<br>(Кэш изображений + Fallback)"]
        UI["Jinja2 + Tailwind CSS + Alpine.js 3"]
        Scroll["HTMX Infinite Scroll<br>(Stateless /partial/albums)"]
        Gallery["PhotoSwipe v5 ESM Lightbox<br>(Aspect Ratio Sync)"]
        Caddy["Caddy Reverse Proxy<br>(Auto TLS / HTTPS)"]
    end

    Yupoo <-->|Обход HTTP 567| PW
    PW --> Discovery & Crawler
    Discovery & Crawler -->|INSERT pending| DB
    DB <-->|SELECT ... FOR UPDATE SKIP LOCKED| Worker
    Worker -->|Скачивание байтов| PW
    Worker -->|Upload photo / Stream| TG_CDN
    TG_CDN -->|file_id| Worker
    Worker -->|Atomic Commit: status=completed| DB

    DB <--> GIN & M2M
    DB <--> App
    App <--> Cache
    TG_CDN -.->|Стриминг фото по file_id| Cache
    App --> UI
    UI <--> Scroll & Gallery
    Caddy <--> App
```

---

## 🚀 Ключевые инженерные решения

* **Обход WAF и защиты от хотлинкинга (HTTP 567):** Прямые HTTP-запросы к Yupoo блокируются защитой Tencent Cloud EdgeOne. Сервис `PlaywrightService` маскирует автоматизацию флагами Chromium, выполняет предварительный прогрев сессии и инжектирует правильные цепочки `Referer`, обеспечивая 99.8% успешных ответов.
* **Telegram-as-a-CDN (Zero-Cost Storage):** Для хранения 240 000+ фотографий (~60 ГБ) используется Telegram Bot API. Изображения скачиваются в ОЗУ (`io.BytesIO`) и загружаются в закрытый канал без записи на диск. В базе сохраняется постоянный `file_id`, исключая расходы на S3-хранилища и износ NVMe SSD.
* **Очередь задач на PostgreSQL (`FOR UPDATE SKIP LOCKED`):** Конкурентная обработка очереди задач несколькими воркерами реализована одной транзакцией прямо в PostgreSQL без привлечения Redis или RabbitMQ. Исключены состояния гонки (Race Conditions) и дублирование загрузок.
* **Нечеткий поиск с толерантностью к опечаткам (`pg_trgm`):** Поиск по 30 000 товаров работает через PostgreSQL триграммное расширение с операторным классом `gin_trgm_ops`. Время выборки составляет 3–8 мс даже при опечатках и смешанных языковых запросах.
* **Гибридный фронтенд (Alpine.js + HTMX):** Серверный рендеринг каталога исключает клиентскую логику пагинации. HTMX подгружает чанки карточек при скролле (Infinite Scroll), а Alpine.js изолированно управляет локальным состоянием поиска, модалок и блокировки скролла на мобильных устройствах.
* **Reseller Protection Invariant:** 8-уровневый конвейер регулярных выражений (`security.py`) гарантированно удаляет из заголовков цены в юанях, контакты китайских поставщиков и технические маркеры маркетплейсов (Weidian/Taobao/1688). Исходные заголовки никогда не передаются в веб-контекст.

---

## 📚 Документация (Матрица Diátaxis)

Вся техническая документация структурирована по международному стандарту **Diátaxis**:

| Слой архитектуры | 🧭 Концепции (Explanation) | 🛠️ Руководства (How-To) | 📖 Справочники (Reference) |
| :--- | :--- | :--- | :--- |
| **01. Acquisition & CDN** | [Архитектура обхода 567 и TG CDN](./docs/01-acquisition-and-cdn/explanation.md) | [Запуск краулера и масштабирование воркеров](./docs/01-acquisition-and-cdn/how-to.md) | [CLI-флаги, security.py и спецификации сервисов](./docs/01-acquisition-and-cdn/reference.md) |
| **02. Database & Storage** | [M2M схема, pg_trgm и оконные функции](./docs/02-database-and-storage/explanation.md) | [Миграции Alembic, бэкапы и проверки целостности](./docs/02-database-and-storage/how-to.md) | [Схемы таблиц, DTO и Query API](./docs/02-database-and-storage/reference.md) |
| **03. Web & Frontend** | [Архитектура FastAPI, HTMX и PhotoSwipe](./docs/03-web-and-frontend/explanation.md) | [Кастомизация витрины, сетки и отладка скриптов](./docs/03-web-and-frontend/how-to.md) | [REST API роуты, карта шаблонов и Design Tokens](./docs/03-web-and-frontend/reference.md) |
| **04. Operations** | [Troubleshooting: база знаний по сбоям](./docs/04-operations/troubleshooting.md) | [Legal Compliance: Ст. 437 ГК РФ и ФЗ-152](./docs/04-operations/legal-and-compliance.md) | — |

---

## 📂 Структура репозитория

```text
website-store/
├── alembic/                # Миграции базы данных (4 версионные ревизии)
├── docs/                   # Техническая документация по стандарту Diátaxis
├── scripts/                # Скрипты парсинга, прогрева и обслуживания данных
│   ├── run_discovery.py    # Сбор карты категорий каталога
│   ├── run_crawler.py      # Сбор ссылок на альбомы с фильтрацией брендов
│   ├── run_worker.py       # Воркер выкачивания и загрузки в Telegram CDN
│   ├── fix_cover.py        # Синхронизация обложек альбомов
│   └── fix_broken_titles.py# Восстановление поврежденных заголовков
├── src/
│   ├── core/               # Конфигурация и инварианты очистки данных (security.py)
│   ├── db/                 # Data Layer: модели, DTO схемы, асинхронный Query API
│   ├── modules/
│   │   ├── crawler/        # Модули краулинга категорий и альбомов
│   │   ├── web/            # FastAPI веб-роутер и сборка страниц
│   │   └── worker/         # Логика атомарной обработки альбома
│   ├── services/           # Интеграции: PlaywrightService, TelegramService, MediaService
│   └── main.py             # Точка входа веб-приложения и Lifespan ServiceRegistry
├── static/                 # CSS/JS ассеты (PhotoSwipe v5 ESM, search.js, menu.js)
├── templates/              # Декомпозированные шаблоны Jinja2 (Mobile-First)
├── docker-compose.yml      # Оркестрация стека (Web + Worker + PostgreSQL)
├── Dockerfile              # Мультистейдж сборка контейнера
└── requirements.txt        # Зафиксированные зависимости
```

---

## ⚡ Быстрый старт (Deployment)

### 1. Настройка переменных окружения

```bash
git clone https://github.com/Curr3ncyV01D/website-store.git
cd website-store
cp .env.example .env
```

Заполните обязательные параметры в `.env`:
```env
# База данных
DB_USER=postgres
DB_PASSWORD=your_strong_password
DB_NAME=yupoo_db
DB_HOST=localhost
DB_PORT=5432

# Telegram CDN
TG_TOKEN=your_bot_token_from_botfather
TG_CHAT_ID=-100xxxxxxxxxx

# Настройки витрины
MANAGER_USERNAME=ManagerSem
```

### 2. Запуск через Docker Compose

```bash
docker compose up -d --build
```

Система инициализирует контейнер PostgreSQL (порт хоста `5433`), применит миграции Alembic, запустит веб-витрину на порту `8765` и активирует фонового воркера.

Проверка состояния системы:
```bash
curl http://localhost:8765/health
```

---

## 🛠️ Стек технологий

* **Бэкенд:** `Python 3.11+`, `FastAPI`, `Uvicorn`, `Pydantic v2`
* **База данных:** `PostgreSQL 15 (Alpine)`, `SQLAlchemy 2.0 (Asyncpg)`, `Alembic`, `pg_trgm`
* **Сбор данных:** `Playwright`, `Playwright-Stealth`, `Asyncio`
* **CDN и хранилище:** `Telegram Bot API (aiogram 3.x)`
* **Фронтенд:** `Jinja2`, `HTMX 1.9.10`, `Alpine.js 3.14.3`, `Tailwind CSS`, `PhotoSwipe v5 ESM`
* **Контейнеризация:** `Docker`, `Docker Compose`
