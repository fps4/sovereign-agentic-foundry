"""Postgres connection pool and user table for tenancy."""
from __future__ import annotations

import os

import asyncpg

DB_URL = os.getenv("DB_URL", "postgresql://platform:changeme@postgres:5432/platform")

_pool: asyncpg.Pool | None = None


async def init_pool() -> None:
    global _pool
    _pool = await asyncpg.create_pool(DB_URL)
    await _pool.execute("""
        CREATE TABLE IF NOT EXISTS users (
            telegram_id   BIGINT PRIMARY KEY,
            telegram_username TEXT,
            gitea_org     TEXT,
            verified      BOOLEAN DEFAULT FALSE,
            verification_code TEXT,
            created_at    TIMESTAMPTZ DEFAULT NOW()
        )
    """)


async def close_pool() -> None:
    if _pool:
        await _pool.close()


async def get_user(telegram_id: int) -> dict | None:
    row = await _pool.fetchrow(
        "SELECT * FROM users WHERE telegram_id = $1", telegram_id
    )
    return dict(row) if row else None


async def upsert_pending_user(
    telegram_id: int, telegram_username: str, code: str
) -> None:
    await _pool.execute(
        """
        INSERT INTO users (telegram_id, telegram_username, verification_code, verified)
        VALUES ($1, $2, $3, FALSE)
        ON CONFLICT (telegram_id) DO UPDATE
            SET telegram_username = $2,
                verification_code = $3,
                verified = FALSE
        """,
        telegram_id,
        telegram_username,
        code,
    )


async def verify_user(telegram_id: int, gitea_org: str) -> None:
    await _pool.execute(
        """
        UPDATE users
        SET verified = TRUE, gitea_org = $2, verification_code = NULL
        WHERE telegram_id = $1
        """,
        telegram_id,
        gitea_org,
    )
