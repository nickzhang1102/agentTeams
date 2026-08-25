"""
Alembic environment configuration for FastAPI (standalone, no Flask dependency)
"""
import logging
import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# Import Base and all models
from db import Base, engine
import models  # Ensure all models are registered

config = context.config

# Override sqlalchemy.url from DATABASE_URL environment variable (Docker support)
database_url = os.environ.get('DATABASE_URL')
if database_url:
    config.set_main_option('sqlalchemy.url', database_url)

fileConfig(config.config_file_name)
logger = logging.getLogger('alembic.env')

target_metadata = Base.metadata

# Tables managed by external libraries (exclude from Alembic)
EXTERNAL_TABLES = {
    'checkpoints', 'checkpoint_blobs', 'checkpoint_writes',
    'checkpoint_migrations',
    'memories', 'claude_chat_memories', 'mem0migrations',
    'approval_states',
    'alembic_version',
}


def include_object(object, name, type_, reflected, compare_to):
    """Filter to exclude external library tables from Alembic management."""
    if type_ == 'table' and name in EXTERNAL_TABLES:
        return False
    return True


def run_migrations_offline():
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()