# Docs Diátaxis Framework Implementation Plan

## Repository Research
- Текущее состояние: FastAPI + PostgreSQL 15 + Playwright + Docker Compose каталог-маркетплейс. Завершены Фаза 1-4 декомпозиции backend + frontend decomposition base.html → skeleton + components. Исправлены 2 post-regression бага (search-bar Alpine race + PhotoSwipe Jinja block-scope leak).
- Контекст документации: пользователь запросил каркас (skeleton docs) по методологии Diátaxis: 3 слоя системы (Acquisition/CDN, Database/Storage, Web/Frontend) + Operations слой. Внутри каждого слоя кроме operations: Explanation (архитектура), How-To (практика), Reference (справочник). Operations слой — Troubleshooting + Legal/Compliance. ИТОГО: 1 index README + 3×3 + 2 = **12 sub-files** = 13 markdown файлов.
- Требования: только каркасы (H1 заголовок + 1-2 предложения аннотация, без полного текста). docs/README.md — интерактивное оглавление с ссылками на все 12 документов.
- Констрейнт: **НЕ создавать docs/ до explicit user approval.** Сначала approve plan.

## Files and Modules to Create
### Directory structure (to be created ONLY after approval)
```
docs/
├── README.md
├── 01-acquisition-and-cdn/
│   ├── explanation.md
│   ├── how-to.md
│   └── reference.md
├── 02-database-and-storage/
│   ├── explanation.md
│   ├── how-to.md
│   └── reference.md
├── 03-web-and-frontend/
│   ├── explanation.md
│   ├── how-to.md
│   └── reference.md
└── 04-operations/
    ├── troubleshooting.md
    └── legal-and-compliance.md
```
**ИТОГО 1 директория корень docs/ + 4 поддиректории + 13 Markdown-файлов каркаса.**

## Implementation Steps (Dependency-ordered)
1. **Mkdirs**: Shell `mkdir` or use Write-file implicit directory-create for every path — create all 5 directories (`docs`, `docs/01-*`, `docs/02-*`, `docs/03-*`, `docs/04-*`).
2. **Per-layer skeleton files (4 layers = 12 files)**. Every file gets exactly:
   - H1 `# <Название файла / раздела>` — на русском, понятное человеку название (например "Объяснение: Архитектура сбора данных и Telegram CDN")
   - Параграф `Аннотация:` + 1-2 предложения назначения файла (как у пользователя в описании структуры: Explanation = Архитектура ...; How-To = Практические инструкции...; Reference = Справочник...; Troubleshooting = База знаний...; Legal = Правовые нормы...).
   - **БЕЗ полного текста контента**, только skeleton H1 + 1-2 sentence annotation.
3. **`docs/README.md` (index)** — Главное оглавление. H1 "Документация semsneak". 4-слойная карта системы (4 секции → 3-2 документа → абсолютные ссылки вида `[Объяснение: Архитектура сбора данных](01-acquisition-and-cdn/explanation.md)`). Вверху — краткий общая схема системы словами — что такое semsneak (маркетплейс-каталог одежды/кроссовок с Yupoo-парсером + Telegram-CDN + веб-витрина FastAPI).
4. **Post-create валидация**: `LS docs/` проверка что все 4 подпапки существуют, 13 md-файлов есть, имена файлов match user-supplied spec exactly (no typos).

## Dependency & Considerations
- Ссылки в docs/README.md — **относительные** (не file://) потому что это Git-репозиторий и GitHub/GitLab Pages будет рендерить их нативно. Пример: `[Объяснение](01-acquisition-and-cdn/explanation.md)`
- НЕЛЬЗЯ нарушать структуру пользователя: не создавать лишние index.md внутри поддиректорий; имена директорий 01-.../02-... match exactly user structure; файлы explanation/how-to/reference/troubleshooting/legal-and-compliance lowercase как у пользователя.
- Аннотации H1 и параграф — **на русском языке** как user query и как вся документация проекта (IMPLEMENTATION_PLAN.md был на русском, все debug md на русском).
- НЕ ПИСАТЬ никакой реальный контент кроме каркаса: не добавлять подзаголовки H2/H3 списки примеры кода — только то что пользователь просил (только H1 + аннотация 1-2 предложения).

## Validation
1. Shell `ls -R docs/` — подсчёт: 4 поддиректории, каждый 01/02/03 содержит 3 md, 04 содержит 2 md, плюс корень README.md = 3×3+2+1 = 13 md-файлов total.
2. Grep `'^# ' docs/ -r` — каждый из 13 файлов должен содержать ровно один H1 в начале файла.
3. Check filenames exact match user spec: `['explanation.md','how-to.md','reference.md']` для 01,02,03 и `['troubleshooting.md','legal-and-compliance.md']` для 04.
4. docs/README.md должен содержать ссылки на ВСЕ 12 под-файлов (12 уникальных относительных href pattern match).

## Risks
1. **Risk: Создадим лишнее содержание.** Mitigation: строго follow spec. Каждый файл = 3 lines максимум: H1 (1), blank (2), annotation paragraph (3). Ни больше. Ни списков, ни H2/H3. Ни кода. Только каркас.
2. **Risk: Ошибки в именах директорий/файлов (capitalize, hyphens vs underscores).** Mitigation: copy-paste имена из user structure verbatim. Check validation step filenames exact match.
3. **Risk: README index содержит битые ссылки.** Mitigation: использовать относительные пути как GitHub-style (case-sensitive на Linux), имена файлов все lowercase как у пользователя. Post-validate grep 12 href matches.
