import asyncio
import os
import sys
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context
from dotenv import load_dotenv

# 1. Настройка путей, чтобы Alembic видел папку src
sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), '..')))

# 2. Импорт Base. 
# ВАЖНО: Убедись, что Base импортируется именно оттуда, где он определен.
from src.db.models import Base 

load_dotenv()

# Объект конфигурации Alembic
config = context.config

# Настройка логирования
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

def get_url():
    """Собирает URL из переменных окружения"""
    user = os.getenv("DB_USER", "postgres")
    pw = os.getenv("DB_PASSWORD", "postgres")
    db = os.getenv("DB_NAME", "yupoo_db")
    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "5432")  # Добавляем порт
    # Используем asyncpg для асинхронного подключения
    return f"postgresql+asyncpg://{user}:{pw}@{host}:{port}/{db}"

def do_run_migrations(connection):
    """Синхронная обертка для запуска миграций внутри асинхронного цикла"""
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()

async def run_migrations_online() -> None:
    """Запуск миграций в 'online' режиме (с подключением к БД)"""
    
    # Создаем секцию конфигурации и подменяем URL
    section = config.get_section(config.config_ini_section)
    section["sqlalchemy.url"] = get_url()

    connectable = async_engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        # Так как Alembic синхронный, используем run_sync
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()

def run_migrations_offline() -> None:
    """Запуск миграций в 'offline' режиме"""
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    # Запускаем асинхронную функцию
    asyncio.run(run_migrations_online())