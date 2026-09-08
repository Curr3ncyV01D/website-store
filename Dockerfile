FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Установка зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Установка браузера Chromium + системные библиотеки Playwright (--with-deps)
RUN playwright install --with-deps chromium

# Копируем весь проект
COPY . .

# Создаём директории для кэша и статики (гарантия, даже если volumes не подключили)
RUN mkdir -p /app/data/media_cache /app/static/images /app/templates

# По умолчанию — interactive shell (переопределяется compose)
CMD ["python"]