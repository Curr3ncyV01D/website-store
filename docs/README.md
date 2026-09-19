# Документация semsneak (каталог-маркетплейс одежды и кроссовок)

**semsneak** — маркетплейс-каталог уличной одежды и кроссовок, построенный на стеке FastAPI + PostgreSQL 15 + Playwright + Telegram-as-a-CDN. Система автоматически парсит внешний каталог поставщиков (Yupoo), синхронизирует изображения через Telegram Bot API как бессерверный медиа-CDN, и предоставляет быструю мобильно-оптимизированную веб-витрину с умным поиском по опечаткам (pg_trgm).

## Общая схема системы

```
┌──────────────────────────────────────────────────────────────────┐
│   01 — Acquisition & CDN (Сбор данных + Telegram CDN)           │
│   Yupoo Parser ⇆ Playwright browser → SKIP LOCKED task queue →   │
│   → Telegram Bot API (хранит оригинальные фото)                 │
└────────────────────────┬─────────────────────────────────────────┘
                         │ (sync catalog rows)
                         ▼
┌──────────────────────────────────────────────────────────────────┐
│   02 — Database & Storage (Хранилище и поиск)                   │
│   PostgreSQL 15-alpine → pg_trgm fulltext index → Alembic →      │
│   → Many-to-Many схема категорий / альбомов / изображений       │
└────────────────────────┬─────────────────────────────────────────┘
                         │ (serve website + media /api/*)
                         ▼
┌──────────────────────────────────────────────────────────────────┐
│   03 — Web & Frontend (Веб-витрина + мобильный UI)              │
│   FastAPI Jinja2 templates → Alpine 3 + HTMX → Tailwind CDN →    │
│   → PhotoSwipe v5 галерея → Caddy TLS termination                │
└────────────────────────┬─────────────────────────────────────────┘
                         │ (day-to-day runbook)
                         ▼
┌──────────────────────────────────────────────────────────────────┐
│   04 — Operations (Эксплуатация, траблшутинг, право)            │
│   Troubleshooting KB → Legal compliance (Ст 437 ГК РФ / TM) →    │
│   → Reseller Protection invariants                               │
└──────────────────────────────────────────────────────────────────┘
```

## Структура документации (Diátaxis Framework)

Каждый слой следует квадрантам Diátaxis: **Explanation (архитектура) → How-To (практика) → Reference (справочник)**, плюс слой Operations с Troubleshooting и Legal.

---

## Слой 1. Сбор данных, парсинг и Telegram CDN

| Тип документа | Название и ссылка |
|---|---|
| 🧭 **Объяснение** | [Архитектура: Обход ошибки 567 Yupoo, Telegram-as-CDN, очереди SKIP LOCKED](01-acquisition-and-cdn/explanation.md) |
| 🛠️ **Практика** | [How-To: Запуск краулера, воркеров, масштабирование, фикс битых заголовков](01-acquisition-and-cdn/how-to.md) |
| 📚 **Справочник** | [Reference: CLI-флаги скриптов, security.py, TelegramService, PlaywrightService](01-acquisition-and-cdn/reference.md) |

---

## Слой 2. База данных и хранилище

| Тип документа | Название и ссылка |
|---|---|
| 🧭 **Объяснение** | [Архитектура: Many-to-Many категории, pg_trgm, хеш-синхронизация обложек](02-database-and-storage/explanation.md) |
| 🛠️ **Практика** | [How-To: Дампы, миграции Alembic, исправление кодировок UTF-8](02-database-and-storage/how-to.md) |
| 📚 **Справочник** | [Reference: DTO schemas.py, структура таблиц PostgreSQL, перечень индексов](02-database-and-storage/reference.md) |

---

## Слой 3. Веб-платформа и витрина

| Тип документа | Название и ссылка |
|---|---|
| 🧭 **Объяснение** | [Архитектура: Mobile-First верстка, HTMX Infinite Scroll, Caddy TLS Termination](03-web-and-frontend/explanation.md) |
| 🛠️ **Практика** | [How-To: Привязка домена/SSL, бренды в карусели, PhotoSwipe галерея](03-web-and-frontend/how-to.md) |
| 📚 **Справочник** | [Reference: REST API эндпоинты, карта Jinja2 шаблонов, JS-скрипты, параметры .env](03-web-and-frontend/reference.md) |

---

## Слой 4. Эксплуатация и нормы

| Тип документа | Название и ссылка |
|---|---|
| 🚑 **Траблшутинг** | [Troubleshooting: База знаний по NoneType, Postgres Auth, CORS/MIME, скролл-баги](04-operations/troubleshooting.md) |
| ⚖️ **Право** | [Legal & Compliance: Публичная оферта (Ст. 437 ГК РФ), товарные знаки, политика данных](04-operations/legal-and-compliance.md) |

---

## Методология: Diátaxis

Вся документация проекта следует фреймворку [Diátaxis](https://diataxis.fr/): каждый технический документ имеет ровно один из четырёх режимов цели:

- **Tutorial / Обучение** — учит новичка сделать что-то успешно (заведомо отсутствует в каркасе MVP, добавится позже)
- **How-To / Практическое руководство** — шаг-за-шагом рецепт для решения конкретной задачи (3 документа)
- **Explanation / Объяснение** — высокоуровневое архитектурное понимание системы и дизайна решений (3 документа)
- **Reference / Справочник** — исчерпывающее описание интерфейсов, сигнатур и фактов о системе (3 документа)
- **Operations-specific** (надстройка над Diátaxis): Troubleshooting KB + Legal Compliance (2 документа, слой эксплуатации).
