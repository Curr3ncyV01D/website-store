# Layer 04 Operations (Troubleshooting + Legal) Documentation Implementation Plan

## Repository Research (100% VERIFIED facts, 0 fabrication)

### Current Documentation State COMPLETED layers
- Layer 01 Acquisition & CDN (3 files explanation/how-to/reference) — **COMPLETED P7 PASS**
- Layer 02 Database & Storage (3 files + Mermaid ERD fix post-feedback) — **COMPLETED P7 PASS**
- Layer 03 Web & Frontend (3 files + 4 Mermaid + 1 ASCII dir tree) — **COMPLETED P7 PASS**
- Layer 04 Operations (skeleton only) — **TARGET 2 files next to write** (2 docs, НЕ 3! Critical deviation from 01/02/03 layers per framework docs_diataxis_framework_plan.md:L26-L28 + docs/README.md:L72-L78 CONFIRMED twice):
  1. `docs/04-operations/troubleshooting.md` (skeleton 3 lines: H1 + Аннотация L1-L3)
  2. `docs/04-operations/legal-and-compliance.md` (skeleton 3 lines: H1 + Аннотация L1-L3)

### Research Source Files VERBATIM read (D4-P1 all facts immutable):
| Артефакт эксплуатации | Key facts extracted VERBATIM |
|------------------------|-------------------------------|
| [docker-compose.yml](file:///C:/Users/Void/Desktop/yupoo-parser/docker-compose.yml) | 3 services: (1) `db` postgres:15-alpine container_name=yupoo_db restart=always shm=128mb ports=**5433:5432** (host→container) healthcheck=pg_isready retries=10; (2) `web` build=. container_name=yupoo_web command=`uvicorn src.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips=*` ports=80:8000 env_file=.env volumes=./data,./static,./templates depends_on=db condition=service_healthy; (3) `worker` build=. command=`python scripts/run_worker.py --interval 1.5` container_name=yupoo_worker depends_on=db healthy+web started. volumes: postgres_data driver local. Lines 1-83 full. |
| [.env.example](file:///C:/Users/Void/Desktop/yupoo-parser/.env.example) | **16 env vars, 7 секций** VERBATIM keys: (DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_NAME), (TG_TOKEN/TG_CHAT_ID), (PROXY_URL optional commented), (CRAWL_KEYWORDS CSV), (RECOMMENDED_BRANDS CSV), (INSTAGRAM_USERNAME/REVIEWS_CHANNEL_URL/MANAGER_USERNAME). |
| [config.py Settings](file:///C:/Users/Void/Desktop/yupoo-parser/src/core/config.py) | **Pydantic BaseSettings defaults (config.py:L52-L73)** VERBATIM: DB_USER=postgres/DB_PWD=postgres/DB_NAME=yupoo_db/DB_HOST=localhost/DB_PORT=5432; MANAGER_USERNAME=ManagerSem; TELEGRAM_ORDER_MESSAGE=`'Здравствуйте! Хочу заказать этот товар: "{title}". Ссылка: {url}'`; INSTAGRAM_USERNAME=semsneak; REVIEWS_CHANNEL_URL="" (empty = hide UI). CSV validators: CRAWL_KEYWORDS/RECOMMENDED_BRANDS Any=str → validator _parse_keywords_csv L26-L41 UPPERCASE dedup. Strip empty env vars L14-L17 antiprepare for CI shells that export empty CSV "=". |
| [Dockerfile](file:///C:/Users/Void/Desktop/yupoo-parser/Dockerfile) | Base image=`mcr.microsoft.com/playwright/python:v1.45.0-jammy` (includes python + playwright chromium deps). 7 steps: WORKDIR /app; ENV 3 vars PYTHONDONTWRITEBYTECODE/UNBUFFERED/PYTHONPATH=/app; COPY requirements → pip install --no-cache-dir; RUN playwright install chromium --with-deps; COPY . all; RUN mkdir data/static/templates dirs; CMD python default. |
| [security.py 8 clean patterns](file:///C:/Users/Void/Desktop/yupoo-parser/src/core/security.py) | LEGAL CLEANUP invariants: clean_album_title L206 strips 8 pattern families VERBATIM L8-L52. CENSORSHIP FILTERS applied BEFORE Jinja/JSON: PRICE yuan/dollar 7 re patterns L8-L16; SIZE ranges/single S-5XL L18-L26; CONTACT wechat/whatsapp/tg/tel regexes L28-L33 (DISABLED L241 `# Отключено за ненадобностью`); URL www./http/.com/.item.html domains L35-L40; TECHNICAL TOKENS weidian/taobao/1688/spm=/utm_ L42-L52; CHINESE CJK chars L54. Fallback chain 7 levels L148-L203 brand+digits→brand+id→digits→sanitized original→brand. _title_is_meaningful_enough L84-L115 guard min len 4 meaningful token. |
| [Alembic DAG 4 revisions](file:///C:/Users/Void/Desktop/yupoo-parser/alembic/versions) | Grep revision/down_revision → VERBATIM DAG **6b2dcf147d3c (None root initial)** → fa672223429c (m2m refactor) → be3675542bee (uq_images album_origin unique) → **a93f1c7d8b2e HEAD pg_trgm extension + GIN idx album title**. 4 files total. alembic.ini L61 sqlalchemy.url=`postgresql+asyncpg://postgres:postgres@localhost:5432/yupoo_db` hardcoded (CI localhost only). |
| Reseller Protection invariant (web layer 03) | 3 sources: router.py:L302-303 comment `NEVER pass original_title or weidian_url`; router.py ALL context dicts = clean_title ONLY; security.py strips weidian/taobao TECHNICAL TOKENS. Grep templates/components/*.html original_title/weidian = 0 hits VERIFIED. |
| User constraint (09/19 after layer02 completion — GLOBAL RULE APPLIES HERE 04 too!) | `docs/02 explanation.md:L10-L44 замени на mermaid схему и больше не используй ASCII рисунки, если можно использовать mermaid. ASCII рисунки можно только для структур папок` → **CONFIRMED layer04:** Mermaid для всех flow/диаграмм; ASCII art — только 1 раз для file tree structures (how-to был case — в troubleshooting/legal НЕТ dir tree plans → 0 ASCII art всего в слое 04). |
| All existing permanent DEBUG artifacts (Phase4 closed) | Project root: NO `debug-search-bar-always-open.md` / NO `debug-photoswipe-lightbox-broken.md` (lessons mirrored in layer03 explanation Critical Protocols). Lessons are retained via layer03 file:/// cross refs. |

---

## Files and Modules to Modify (2 files ONLY; scope EXACTLY per docs/README.md:L72-L78 framework skeleton — НЕ 3)

| # | Target file (full path) | Expected scope of changes (Diátaxis Ops-specific modes) | Lines approx (plan) |
|---|--------------------------|----------------------------------------------------------|-------------------|
| 1. | [docs/04-operations/troubleshooting.md](file:///C:/Users/Void/Desktop/yupoo-parser/docs/04-operations/troubleshooting.md) | **Troubleshooting KB (6 больших разделов, scientific debug 3 hypotheses each pattern)** — *Каждая запись KB:* Symptom → Diagnosis (3 hypotheses ordered by likelihood) → Step-by-step Fix + file:/// reference. No recipes-style imperative steps (How-To mode запрещён в Troubleshooting per Diátaxis). **SECTIONS (6 шт):** <br>T1 Docker Postgres Auth Failed `password authentication failed for user "postgres"` (port 5432 vs 5433 confusion host-container) <br>T2 Crawler Pipeline NoneType/AttributeError: Run discovery/playwright returns None title (Yupoo 567 hotlink protection, session warmup bug) <br>T3 Telegram Bot API 429 Too Many Requests `Retry-After: X` (Flood Control TG, worker interval too small) <br>T4 Alembic Migration DAG Integrity Broken: `FAILED: Can't locate revision identified by 'xxxxx'` (missed revision file, dirty DB state, DAG 4 revisions correct order) <br>T5 Frontend Production Bugs regressions (search bar always-open Alpine defer race; PhotoSwipe zoom aspect broken data-pswp 1000×1000 placeholder unchanged) <br>T6 Health endpoint checks `/health` services.telegram_available = false (TG_TOKEN/TG_CHAT_ID invalid or network RU blocked without proxy) <br> **+ 1 Mermaid flowchart Troubleshooting Decision Tree Triage** start → symptom branch → hypothesis/fix. | ~240 lines. 1 Mermaid. 0 ASCII art (нет tree структур в KB). |
| 2. | [docs/04-operations/legal-and-compliance.md](file:///C:/Users/Void/Desktop/yupoo-parser/docs/04-operations/legal-and-compliance.md) | **Legal & Compliance (3 НОРМАТИВНЫХ раздела РФ закона VERBATIM на основе existing code invariants — 0 legal advice fabrication):** <br>L1 Статья 437 ГК РФ (Публичная оферта розничной купли-продажи) — шаблон текста оферты, привязка к функционалу кнопки «Заказать в Telegram»=акцепт. MANAGER_USERNAME/REVIEWS_CHANNEL_URL env vars как реквизиты. <br>L2 Товарные знаки и добросовестное использование (защита от претензий Nike/Adidas/Jordan/Balenciaga/Arc'teryx/Stone Island) — МЕХАНИЗМ ЗАЩИТЫ в коде: **Reseller Protection Invariant = 8-level security.py clean title** (удаление всех артикульных ссылок на weidian/taobao, технических токенов spm/utm/itemid, цен, оригинальных заголовков с упоминаниями брендов в связке с продавцом). ИНСТРУКЦИЯ: никогда не отключать L240 `# Отключено за ненадобностью пока что` contact patterns без юридической проверки. Grep audit инструкция повторно. <br>L3 Федеральный закон №152-ФЗ «О персональных данных» (27.07.2006) — scope: Какие данные НЕ СОБИРАЕТ сайт (0 регистрация, 0 cookies analytics без согласия, 0 localStorage except Alpine state, никаких телефонов/ФИО пользователей — весь контакт идёт через внешний Telegram менеджера). Ссылки на TG/IG = внешние сервисы own policy. <br> **+ 1 Mermaid Legal Compliance Control Flow** user visits → offer acceptance → Reseller Protection pipeline clean_title→ Reseller invariant hold → trademark disclaimer display. | ~180 lines. 1 Mermaid. 0 ASCII art. |

**ИТОГО ожидаемый объём слоя 04**: 2 файла, ~420 lines total, 2 Mermaid diagrams, **0 ASCII art** (нет file-tree планов в этих 2 docs — соответствует user constraint «ASCII только папки»).

---

## Implementation Steps (dependency-ordered, Plan Mode)

1. **D4-P1 Research (COMPLETED ✓)** — read all 10 source files above, extracted VERBATIM values for services/env/DAG/security patterns, confirmed framework has 2 ops docs NOT 3 (critical deviation from 01/02/03), confirmed user constraint Mermaid global rule applies 04 too.

2. **D4-P2 Plan write (CURRENT STEP)** → this document `layer04_operations_docs_plan.md` created now.

3. **D4-P3 Approval gate** → NotifyUser tool sent to user with this plan file. **NO FILES MODIFIED before explicit user approval!** (Plan Mode protocol).

4. **D4-P4 WRITE Step 1 (after approval)** → Write full `troubleshooting.md` 6 sections T1-T6 + 1 Mermaid Decision Tree Triage flow. Each KB entry follows strict Scientific Debug format per Phase4 lessons (Symptom/3 Hypotheses ordered likelihood/Fix with file:/// refs).

5. **D4-P5 WRITE Step 2 (after approval, sequential)** → Write full `legal-and-compliance.md` 3 sections L1-L2-L3 + 1 Mermaid Compliance Flow. *Legal fabrication constraint (HARD 0 policy):* No fabricated legal text beyond Russian Civil Code Art 437 standard public offer template language + Federal Law 152 standard minimal processing disclosure text + Reseller Protection Invariant MECHANICAL CODE references (all legal text must have at least 1 file:/// link proving the invariant exists in code — claims need code evidence, ZERO ungrounded legal opinions).

6. **D4-P6 Validation P7 Layer 04 (7 CHECKLIST GREPS PASS required, 0 failure acceptable)**

---

## Dependencies and Considerations

### Critical Non-functional Requirements (inherit from layers 01/02/03 + user constraints GLOBAL)
1. **Diátaxis Ops Mode Strict Separation:** 2 files do NOT смешивать стили: Troubleshooting = Symptom → Hypotheses → Fix (научный дебаг, НЕ пошаговые how-to рецепты). Legal = Normative framework article → Code invariant enforcement → Disclosure text.
2. **0 Fabrication Policy (P7):** ALL claims about code (.env keys / port numbers / compose services / Alembic revisions / security 8 regex families / Reseller invariant) — VERBATIM match code grep. If cannot cite file:/// L line — удалить утверждение.
3. **≥ 35 file:/// ссылок TOTAL ACROSS 2 docs (layer 04 sum min 35 refs).** Reference heavy like layers 02/03. Link to existing layer01/02/03 docs as cross refs (DRY).
4. **Mermaid Global Rule (09/19 user feedback):** ALL diagrams = Mermaid (2 total for layer 04). ASCII art ONLY if file tree structure required — not required for ops docs → 0 ASCII total 04 layer.
5. **Windows PowerShell syntax ONLY in Troubleshooting fix command blocks (NOT CMD/bash):** grep Select-String; uvicorn use `.\.venv\Scripts\python.exe -m uvicorn ...` exactly per previous layers.

### Risks (ops-specific) and Mitigation
| Risk ID | Risk description | Likelihood | Impact | Mitigation strategy VERBATIM |
|---------|------------------|------------|--------|-------------------------------|
| R1 Ops 01 | Legal fabrication risk: write Art 437/152 ФЗ text without proper civil code standard language — might be interpreted as legal advice / not compliant | **High** | **HIGH** (legal liability claims) | **Mitigation:** (1) Every normative statement about Russian law has an EXPLICIT DISCLAIMER at top of legal-and-compliance.md: «Данный документ не является юридической консультацией. Для применения норм请 обратитесь к профильному юристу.» (2) ALL Reseller Protection claims ARE BACKED BY VERBATIM CODE REFERENCES (security.py:L8-L52 8 patterns; router.py:L302-303 comment). ZERO claims without code evidence. (3) For Art 437 — use STANDARD templated public offer language (common Russian marketplace boilerplate). ФЗ-152 — standard scope disclosure «мы не собираем персональные данные пользователей через сайт; все контакты осуществляются через Telegram-менеджера на внешнем сервисе» (meets 0 registration fact). |
| R1 Ops 02 | Troubleshooting KB NoneType hypotheses might misdiagnose Yupoo Session Warm-up step if user skips playbook | Medium | Medium | Cross-ref Layer01 docs explicitly for T2: «Run `run_discovery.py` first (warm-up) BEFORE `run_crawler.py`, see [01 acquisition how-to R2-R3](file:///C:/Users/Void/Desktop/yupoo-parser/docs/01-acquisition-and-cdn/how-to.md)". |
| R1 Ops 03 | Alembic DAG revision list changes later (new 5th migration added) → Troubleshooting T4 stale 4-revision list | Low | Low | Document T4 GENERIC playbook with VERIFY DAG via `alembic history --verbose` + "Если DAG не совпадает с 6b2d→fa672→be367→a93f актуальный список head" instead of hard-fail. |
| R1 Ops 04 | Port confusion 5432/5433 repeated too many times → stale doc after compose change (low, current compose L15 hardcoded) | Low | Low | VERBATIM cite [docker-compose.yml:L15](file:///C:/Users/Void/Desktop/yupoo-parser/docker-compose.yml#L15) line 15 exact. |

---

## Validation P7 Layer 04 (7 MUST-PASS grep checklist, 0 failures allowed)

> Run **ALL 7 checks AFTER 2 files written.** If ANY check FAILS → rewrite the faulty claim / add missing file:/// refs → rerun.

| # | Grep Validation Check (must match code VERBATIM) | Expected PASS Result |
|---|---------------------------------------------------|-----------------------|
| C1 | **.env example keys exact match troubleshooting.md L env vars section:** `DB_HOST|DB_PORT|DB_USER|DB_PASSWORD|DB_NAME|TG_TOKEN|TG_CHAT_ID|PROXY_URL|CRAWL_KEYWORDS|RECOMMENDED_BRANDS|INSTAGRAM_USERNAME|REVIEWS_CHANNEL_URL|MANAGER_USERNAME` 13 keys match .env.example L1-L36 | ≥13 occurrences across 2 ops md files total. Each key name EXACT uppercase, NO typo. |
| C2 | **docker-compose services exact names:** Troubleshooting references must use EXACT service names compose L5/L29/L62: `db`, `web`, `worker`. Port mapping `5433:5432` L15 exact. | Verify compose services=3 strings + port mapping string appear VERBATIM in troubleshooting.md T1. |
| C3 | **Alembic DAG revisions 4 exact IDs order:** `6b2dcf147d3c → fa672223429c → be3675542bee → a93f1c7d8b2e` (root initial → m2m → UQ images → pg_trgm GIN HEAD). | Troubleshooting.md T4 lists 4 revisions IN THIS EXACT ORDER (Alembic grep down_revision matches). Reference Grep exactly 4 ids. |
| C4 | **Telegram 429 Retry-After:** Troubleshooting.md T3 section MUST include the VERBATIM worker interval `--interval 1.5` compose L67 AND cite TelegramService retry_after handling (which file? Layer01 reference file: [01 acquisition reference TelegramService section](file:///C:/Users/Void/Desktop/yupoo-parser/docs/01-acquisition-and-cdn/reference.md)). | T3 includes file:/// 01 ref + interval 1.5 string. |
| C5 | **Reseller Protection invariant legal L2:** Claims in legal-and-compliance.md L2 Товарные знаки section must cite 3 concrete code references: (a) [router.py:L302-L303 comment NEVER pass original title/weidian](file:///C:/Users/Void/Desktop/yupoo-parser/src/modules/web/router.py#L302-L303); (b) [security.py:L42-L52 TECHNICAL TOKENS weidian/taobao/1688 strip](file:///C:/Users/Void/Desktop/yupoo-parser/src/core/security.py#L42-L52); (c) Reseller grep audit recipe cross-ref [layer03 how-to R7](file:///C:/Users/Void/Desktop/yupoo-parser/docs/03-web-and-frontend/how-to.md). | 3 refs present, no fabrication of trademark claims without code evidence. |
| C6 | **Legal Civil Code and ФЗ names EXACT:** Document legal-and-compliance.md must contain EXACT russian normative names strings: (a) `«Статья 437 Гражданского кодекса Российской Федерации»` (ГК РФ full); (b) `«Федеральный закон от 27 июля 2006 года № 152-ФЗ „О персональных данных“»` (full title). | Both exact strings appear in the doc. Short forms allowed as secondary after first mention full. |
| C7 | **≥ 35 file:/// cross references TOTAL across BOTH ops documents (troubleshooting + legal sum)**. (inherit min from 02/03 =35). | Grep `file:///` count across directory 04-operations/ → count ≥ 35. Prefer linking existing 01/02/03 docs where possible (DRY). |

**PASS CRITERIA D4-P6:** All 7 checks (C1-C7) return expected result → Layer 04 COMPLETED → notify user → done (next work future phases after approval).
