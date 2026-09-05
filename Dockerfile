FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

WORKDIR /app

# Установка зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Установка браузеров Playwright
RUN playwright install chromium

# Копируем проект
COPY . .

# По умолчанию ничего не запускаем, будем переопределять в compose или скриптах
CMD ["python"]