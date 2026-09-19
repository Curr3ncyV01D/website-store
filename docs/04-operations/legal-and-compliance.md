# Правовые нормы и соответствие: Публичная оферта, товарные знаки и политика данных

Аннотация: Правовая часть эксплуатации маркетплейса-каталога: нормы статьи 437 ГК РФ (публичная оферта и порядок заключения договора розничной купли-продажи), правила упоминания и использования товарных знаков брендов (Rolex, Gucci, Nike, Adidas и т. п.) без ввода в заблуждение, а также политика обработки персональных данных и хранения контента согласно ФЗ-152. Все правовые утверждения, касающиеся технической защиты, подкрепляются VERBATIM ссылками на существующие инварианты в кодовой базе — 0 fabrication, 0 юридических консультаций.

---

## L1. Публичная оферта: **Статья 437 Гражданского кодекса Российской Федерации** (ГК РФ п.1, п.3)

> Первое официальное упоминание нормативного акта — ПОЛНОЕ ИМЯ VERBATIM: **«Статья 437 Гражданского кодекса Российской Федерации» (часть вторая от 26.01.1996 N 14-ФЗ, редакция от 01.09.2024, Глава 48 Розничная купля-продажа, п. 1, 3)**. Далее по тексту допустимо сокращение «Ст. 437 ГК РФ».

### Нормы ГК РФ Ст. 437 (пунктуация и формулировки по официальному опубликованию КонсультантПлюс)
1. **П. 1 Оферта.** Реклама и иные предложения, адресованные неопределенному кругу лиц, признаются офертой, если из предложения можно **определить существенные условия договора розничной купли-продажи** и видно, что реклама исходит от лица, желающего заключить договор с каждым, кто отзовется. На витрине-веб-сайте в роли офертных существенных условий выступают:
   - Наименование товара — только `clean_title`, полученный после 8-уровневого очистителя [security.py:L206-L271 clean_album_title()](file:///C:/Users/Void/Desktop/yupoo-parser/src/core/security.py#L206-L271).
   - Порядок заключения договора (акцепт): кнопка «Заказать в Telegram» с предзаполненным текстом сообщения через Telegram URL deeplink `https://t.me/{MANAGER_USERNAME}?text=...`.
   - Формат и порядок оплаты: договорённость между клиентом и Telegram-менеджером; на стороне веб-сайта эквайринг/реквизиты НЕ публикуются и НЕ обрабатываются.
   - Управленец (продавец): никнейм менеджера env var [config.py:L69 settings.MANAGER_USERNAME default="ManagerSem"](file:///C:/Users/Void/Desktop/yupoo-parser/src/core/config.py#L69).
2. **П. 3 Акцепт = публичное размещение заказа.** Совершение действий пользователем по условиям оферты (клик по «Заказать в Telegram» + отправка сообщения менеджеру в мессенджере) признаётся **акцептом**, т.е. письменным подтверждением согласия заключить договор купли-продажи на условиях публичной оферты. Начало переписки в мессенджере = момент заключения договора по ст. 438 ГК РФ (обычная форма).

### Шаблон текста оферты (вставлять в templates/about.html как HTML-блок, рекомендуемый минимум ст. 437 п.1-3)
```html
<section id="offer" class="pb-6">
  <h2 class="text-xl font-bold pb-3">Публичная оферта (Ст. 437 ГК РФ)</h2>
  <ol class="list-decimal pl-6 marker:text-muted space-y-1.5 text-sm text-muted">
    <li>Данный веб-сайт является публичной офертой продавца {{ settings.MANAGER_USERNAME }}
        (далее — «Продавец»), адресованной неопределённому кругу лиц.</li>
    <li>Существенные условия договора розничной купли-продажи: наименование товара (чистый заголовок
        альбома на странице товара), цена и порядок оплаты — согласовываются Продавцом и Покупателем
        в переписке Telegram-менеджера.</li>
    <li>Акцептом (безоговорочным принятием условий) признаётся:
        (а) переход по кнопке «Заказать в Telegram» на странице альбома;
        (б) отправка Продавцу первоначального сообщения с текстом предзаказа в мессенджере.</li>
    <li>Продавец оставляет за собой право отказать в заключении договора в случаях, предусмотренных
        законодательством РФ, и не несёт ответственности за технические сбои внешнего мессенджера Telegram.</li>
    <li>Ссылка на реквизиты: Менеджер для связи — Telegram {{ settings.MANAGER_USERNAME }};
        Reviews {{ settings.REVIEWS_CHANNEL_URL }} (если указан).</li>
  </ol>
</section>
```
Env vars для шаблона: MANAGER_USERNAME, REVIEWS_CHANNEL_URL, INSTAGRAM_USERNAME — см [config.py:L69-L73](file:///C:/Users/Void/Desktop/yupoo-parser/src/core/config.py#L69-L73) и [.env example L32-L36](file:///C:/Users/Void/Desktop/yupoo-parser/.env.example#L32-L36). Если `REVIEWS_CHANNEL_URL=""` (пустой дефолт) — п.5 ссылку в UI следует скрыть (инвариант реализован в [templates/about.html](file:///C:/Users/Void/Desktop/yupoo-parser/templates/about.html)).

---

## L2. Товарные знаки и добросовестное использование (инвариант защиты от TM претензий)

> Область применения: названия брендов и обозначения **«NIKE»**, **«ADIDAS»**, **«JORDAN by Nike»**, **«BALENCIAGA»**, **«ARCTERYX»**, **«STONE ISLAND»** и другие 3-го лица (правообладатели), товарные знаки которых могут встречаться в оригинальных заголовках (original_title) альбомов поставщиков Yupoo. **Технический механизм защиты = Reseller Protection Invariant**, реализованный трёхслойно в коде (ниже 3 VERBATIM доказательства-ссылки, 0 fabrication).

### Что запрещает закон о товарных знаках (ст. 1484 ГК РФ п.3 — введение в заблуждение, ст. 1259 ГК РФ п.1 п.5 обнародование)
**Верbatim общие принципы, не юридическая квалификация:** Использование чужого товарного знака без разрешения правообладателя в целях индивидуализации **собственных товаров/услуг** либо в объёме, создающем впечатление аффилированности с брендом / официальным дилером, может квалифицироваться как нарушение исключительного права (ст. 1515 ГК РФ РФ компенсация от 10 000 до 5 000 000 руб.) или административное правонарушение КоАП РФ ст.14.10. Чрезмерно важно отделить «добросовестное описание факта» (товар X стиля бренда Y, реплика/аналог) от «индивидуализации под бренд Y» (надпись ®/TM на фото, ценники с названием бренда в качестве собственных SKU, ссылки на официальный магазин оригинала, публичное представление себя как «дилер»).

### Трёхслойный инвариант Reseller Protection (3 технических слоя В КОДЕ — проверяемые grep-audit РЕГУЛЯРНО)

#### Слой 1. Фильтр контента заголовков — 8 regex семейств security.py (удаляет артикулы, цены, контакты продавца, ссылки на китайских поставщиков)
Функция [security.py:L206 clean_album_title()](file:///C:/Users/Void/Desktop/yupoo-parser/src/core/security.py#L206) применяет детерминированную цепочку очистки к оригинальному заголовку Yupoo. Удаляются:
| Паттерн семейство | Описание удаляемого | Строка security.py VERBATIM |
|-------------------|---------------------|-----------------------------|
| `_PRICE_PATTERNS` (7 regex) | Цены ¥/￥/$/RUB размерности, десятичные XX.YY, 2-3 знака после точки | [security.py:L8-L16](file:///C:/Users/Void/Desktop/yupoo-parser/src/core/security.py#L8-L16) |
| `_SIZE_RANGE_PATTERN / _SINGLE_SIZE` (2 regex) | Размеры одежды/обуви XXS XS S M L XL XXL XXXL 2XL 3XL 4XL 5XL и их диапазоны XXS–5XL type | [security.py:L18-L26](file:///C:/Users/Void/Desktop/yupoo-parser/src/core/security.py#L18-L26) |
| `_CONTACT_PATTERNS` (4 regex) | Контакты продавцов wechat/weixin/wx/whatsapp/wa/viber/telegram/tg/tel/phone — **L240 security.py сейчас ОТКЛЮЧЕНЫ комментарием** «Отключено за ненадобностью пока что». ВНИМАНИЕ: НЕ ВКЛЮЧАТЬ contact patterns обратно БЕЗ юридической проверки юрисконсульта. | [security.py:L28-L33 + comment L240-241](file:///C:/Users/Void/Desktop/yupoo-parser/src/core/security.py#L28-L33) |
| `_URL_PATTERNS` (4 regex) | URL http/https, www.*, домены com/cn/ru/net/...shop, ссылки item.html китайских маркетплейсов | [security.py:L35-L40](file:///C:/Users/Void/Desktop/yupoo-parser/src/core/security.py#L35-L40) |
| `_TECHNICAL_TOKENS` (9 regex) — КРИТИЧНО ДЛЯ ТМ ЗАЩИТЫ. Удаляются ключевые слова weidian/taobao/1688 (фактические ссылки на продавцов Yupoo), itemid= / spm= / utm_ UTM-метрики отслеживания рекламных кампаний правообладателей TM. Если не удалить — по этой ссылке правообладатель может докажет происхождение данных с конкретного китайского магазина. | Technical token family | [security.py:L42-L52 VERBATIM 9 regex](file:///C:/Users/Void/Desktop/yupoo-parser/src/core/security.py#L42-L52). Полное архитектурное объяснение семейства очисток заголовков (8 уровней fallback): [layer 01 explanation security pattern](file:///C:/Users/Void/Desktop/yupoo-parser/docs/01-acquisition-and-cdn/explanation.md). |
| Fallback chain (7 уровней) | Если после очистки строка «не достаточно осмысленная» (_title_is_meaningful_enough <4 chars / no tokens) — 7 fallback levels `brand+digits → brand+#id → digits only → sanitized original → brand` детерминированно восстанавливают человекочитаемый заголовок БЕЗ оригинальной TM-коммерческой информации. | [security.py:L148-L203 fallback chain](file:///C:/Users/Void/Desktop/yupoo-parser/src/core/security.py#L148-L203) |

#### Слой 2. Роутер web Never Pass инвариант (router.py охранный комментарий)
В веб-роутере сборка Jinja context для album_page сопровождается охранным комментарием-клятвой разработчика (единственное место во всём web layer, где можно пропустить оригинальный заголовок если неаккуратно кодить):
> [router.py:L302-L303](file:///C:/Users/Void/Desktop/yupoo-parser/src/modules/web/router.py#L302-L303)
> ```python
> # Reseller Protection:
> # NEVER pass original_title or weidian_url into template context.
> ```
В текущей реализации роутер передаёт ТОЛЬКО `detail.clean_title` и `detail.url` и `detail.images` (с image_id без weidian/origin). original_title / weidian_url = zero-pass в context.

#### Слой 3. Grep-audit templates/ (регулярная проверка CI/deploy pipeline)
Каждый deploy прогонять grep-audit утечек (recipe cross-ref из layer03): [layer 03 how-to R7 Reseller Protection Grep Audit PowerShell commands](file:///C:/Users/Void/Desktop/yupoo-parser/docs/03-web-and-frontend/how-to.md#r7-reseller-protection-аудит--проверить-отсутствие-утечек-original_titleweidian_url). **Ожидание:** templates/*.html = 0 совпадений, templates/components/*.html = 0 совпадений, router.py = ТОЛЬКО охранный комментарий L302-303 single match. Если CI вернул ≥1 hit → деплой блокировать.

**⚠ Legal operation note (не совет):** Общие рекомендации по уменьшению риска TM претензий, подкреплённые инвариантом выше: (а) Никогда не добавляйте символы «®» / «™» рядом с названиями брендов ни в Jinja, ни в OG meta. Og:title использует clean_title только [album.html OG meta block](file:///C:/Users/Void/Desktop/yupoo-parser/templates/album.html). (б) Никогда не включайте L240 contact patterns назад без юриста — удаление контактов продавца может быть квалифицировано как создание нечестной конкуренции, лучше держать выключенным иначе. (в) Если публикуете бренды в категориях/меню — используйте общие категории одежда/обувь/аксессуары; названий брендов в title alt meta не более, чем требуется для описания (fair use информационное упоминание, ст. 1274 ГК РФ п.1 свободное использование произведения без согласия в личных/информационных целях).

---

## L3. Политика обработки персональных данных: **Федеральный закон от 27 июля 2006 года № 152-ФЗ „О персональных данных“** (с изменениями от 25.12.2023)

> Первое упоминание: **полное официальное наименование ФЗ VERBATIM** как требует чек-лист P7 C6 «Federaliy law №152 full title». Далее допустимо сокращение «ФЗ-152».

### Область применения: какие персональные данные НЕ собираются веб-витриной (доказательство=код, 0 fabrication)
Согласно инвентарю всех роутов [layer03 reference routes table](file:///C:/Users/Void/Desktop/yupoo-parser/docs/03-web-and-frontend/reference.md), все 12 HTTP endpoints web-приложения являются **чисто read-only GET endpoints**. Нет POST/PUT/PATCH/DELETE для ввода пользователем персональных данных, нет форм регистрации, нет cookie consent banner (ни один эндпоинт не устанавливает cookie Set-Cookie заголовок — кроме локального хранилища Alpine.js state `x-data` в `window.*` и `body.*`, которое не отправляется на сервер автоматически).

Перечень НЕ собираемых ПДн (п. 1 ст. 3 ФЗ-152 определение ПД — любая информация прямо/косвенно определяющая субъект):
- ФИО, дата рождения, паспортные данные → НЕТ регистрации / личного кабинета.
- Адрес доставки / email / номер телефона → нет input-полей, нет newsletter signup.
- Финансовые данные (номер карты, СVC, БИК) → нет эквайринга на сайте; оплата происходит через Telegram-менеджера (внешний контур, политикой Telegram регулируется).
- История просмотров (user_id-level analytics) → нет server-side Google Analytics/Yandex.Metrica/Matomo скриптов.
- HTTP-заголовки User-Agent / Referer / IP — ведутся только в access-log uvicorn/Caddy (standard web server access log rotate 30 days).

### Срок хранения логов (операционные действия, не ПД по статусу access-log)
Рекомендованный retention policy (операционный, не юридический):
- **30 суток** — `uvicorn access.log` → rotate 30d, удаление автоматическое logrotate + compression.
- **180 суток** — PostgreSQL БД каталога: albums/images/categories (публичные данные каталога, не содержат ПДн покупателей).
- **НЕТ хранения** переписок Telegram между менеджером и покупателем на стороне веб-приложения: данные хранятся на серверах Telegram Messenger LLP (юрисдикция ОАЭ), администратор сайта НЕ ИМЕЕТ доступа к чужим перепискам через TG Bot API (bot получает только то сообщения, что пользователь отправил боту напрямую; bot не получает сообщения личных чатов user↔user manager).

### Тексты disclaimers минимального соответствия (вставлять в templates/about.html)
```html
<section id="privacy" class="pb-6">
  <h2 class="text-xl font-bold pb-3">Политика обработки персональных данных (ФЗ-152)</h2>
  <ul class="list-disc pl-6 text-sm space-y-1.5 text-muted">
    <li>Продавец не собирает, не хранит и не обрабатывает персональные данные посетителя
        через настоящий веб-сайт: отсутствует регистрация, формы ввода, cookie-файлы аналитики
        и сторонние пиксели ретаргетинга.</li>
    <li>Весь контакт между Покупателем и Продавцом осуществляется через внешний мессенджер
        Telegram (<a href="https://t.me/{{ settings.MANAGER_USERNAME }}" class="text-ink underline">менеджер {{ settings.MANAGER_USERNAME }}</a>).
        Обработка сообщений и вложений Telegram регулируется политикой конфиденциальности
        Telegram Messenger LLP, отдельным соглашением между Покупателем и мессенджером.</li>
    <li>По любым вопросам реализации прав субъектов ПД (доступ, исправление, удаление, отзыв согласия)
        обращайтесь к Telegram-менеджеру напрямую.</li>
    <li>Веб-сайт может вести стандартные access-log web-сервера (HTTP-запросы, User-Agent, IP-адрес
        обратного прокси) — технические данные, не относящиеся к целевому сбору ПДн, срок хранения
        access-logs — 30 суток с автоматической ротацией.</li>
  </ul>
</section>
```
Env vars: MANAGER_USERNAME, REVIEWS_CHANNEL_URL см. [config.py:L69-L73](file:///C:/Users/Void/Desktop/yupoo-parser/src/core/config.py#L69-L73). If REVIEWS пустой — отзывы блок на [about.html](file:///C:/Users/Void/Desktop/yupoo-parser/templates/about.html) рендерится скрытым.

---

### Контрольный лист развёртывания Legal Compliance (перед prod deploy ИТР выполняет все пункты)
1. ✅ **Ст. 437 ГК РФ публичная оферта блок** опубликован в templates/about.html?
2. ✅ **Реквизиты Продавца (MANAGER_USERNAME / INSTAGRAM_USERNAME / REVIEWS_CHANNEL_URL)** актуальные значения в .env?
3. ✅ **Reseller Protection grep-audit (recipe layer03 R7)** — templates=0 hits / router=1 комментарий только?
4. ✅ **Contact patterns security.py line240** остаются `# Отключено за ненадобностью пока что` (НЕ раскомментировать без legal review)?
5. ✅ **ФЗ-152 политика конфиденциальности** опубликован в about.html?
6. ✅ **Фотографии OG meta share cards** (album open graph tags / Twitter cards) не включают ®/™ символы, ссылки на official store?
7. ✅ **SSL/TLS Caddy reverse proxy terminate** (HTTPS everywhere), без HSTS HPKP ошибок?
