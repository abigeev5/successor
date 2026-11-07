"""Alembic environment. URL: `sqlalchemy.url` option if set (tests), otherwise DATABASE_URL from settings."""

import re
from logging.config import fileConfig
from typing import Any

from alembic import context
from alembic.operations import ops
from pgvector.sqlalchemy import Vector
from sqlalchemy import CheckConstraint, Column, Enum, create_engine, pool

from app.core.config import get_settings
from app.core.db import Base
from app.wiring import import_models

config = context.config
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

import_models()
target_metadata = Base.metadata


def _drop_duplicate_enum_checks(_context, _revision, directives) -> None:  # type: ignore[no-untyped-def]
    """Enum(create_constraint=True) creates its CHECK itself; autogenerate also renders it explicitly,
    and the migration fails with DuplicateObject. Drop the explicit copies."""
    for op_ in directives[0].upgrade_ops.ops:
        if not isinstance(op_, ops.CreateTableOp):
            continue
        enum_cols = {c.name for c in op_.columns if isinstance(c, Column) and isinstance(c.type, Enum)}
        op_.columns = [
            c
            for c in op_.columns
            if not (
                isinstance(c, CheckConstraint)
                and any(re.match(rf"^(\w+\.)?{name} IN \(", str(c.sqltext)) for name in enum_cols)
            )
        ]


def _render_item(type_: str, obj: object, autogen_context: Any) -> str | bool:
    """Enum: without create_constraint (the explicit CHECK in the table is the only copy).
    pgvector: with its import, which autogenerate does not add by itself."""
    if type_ == "type" and isinstance(obj, Vector):
        autogen_context.imports.add("import pgvector.sqlalchemy")
        return f"pgvector.sqlalchemy.Vector({obj.dim})"
    if type_ == "type" and isinstance(obj, Enum):
        values = ", ".join(repr(v) for v in obj.enums)
        return (
            f"sa.Enum({values}, name={obj.name!r}, native_enum=False, "
            f"length={obj.length}, create_constraint=False)"
        )
    return False


def _url() -> str:
    return config.get_main_option("sqlalchemy.url") or get_settings().database_url


def run_migrations_offline() -> None:
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            process_revision_directives=_drop_duplicate_enum_checks,
            render_item=_render_item,
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
