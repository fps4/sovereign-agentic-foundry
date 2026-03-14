"""Postgres connection pool — users, conversation history, app registry."""
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
    await _pool.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id         SERIAL PRIMARY KEY,
            user_id    TEXT NOT NULL,
            role       TEXT NOT NULL,
            content    TEXT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    await _pool.execute("""
        CREATE TABLE IF NOT EXISTS apps (
            id           SERIAL PRIMARY KEY,
            telegram_id  BIGINT NOT NULL REFERENCES users(telegram_id),
            name         TEXT NOT NULL,
            description  TEXT NOT NULL DEFAULT '',
            app_type     TEXT NOT NULL DEFAULT '',
            status       TEXT NOT NULL DEFAULT 'queued',
            repo_url     TEXT,
            app_url      TEXT,
            error_detail TEXT,
            created_at   TIMESTAMPTZ DEFAULT NOW(),
            updated_at   TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE (telegram_id, name)
        )
    """)
    await _pool.execute("""
        CREATE TABLE IF NOT EXISTS app_issues (
            id              SERIAL PRIMARY KEY,
            app_id          INTEGER NOT NULL REFERENCES apps(id),
            error_hash      TEXT NOT NULL,
            gitea_issue_url TEXT,
            is_breaking     BOOLEAN NOT NULL DEFAULT FALSE,
            created_at      TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE (app_id, error_hash)
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


async def append_message(user_id: str, role: str, content: str) -> None:
    await _pool.execute(
        "INSERT INTO messages (user_id, role, content) VALUES ($1, $2, $3)",
        user_id,
        role,
        content,
    )


async def get_history(user_id: str, limit: int = 20) -> list[dict]:
    rows = await _pool.fetch(
        """
        SELECT role, content FROM messages
        WHERE user_id = $1
        ORDER BY created_at DESC
        LIMIT $2
        """,
        user_id,
        limit,
    )
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


# ── App registry ──────────────────────────────────────────────────────────────

async def register_app(
    telegram_id: int, name: str, description: str, app_type: str
) -> int:
    """Insert a new app with status=queued. Returns the app id."""
    row = await _pool.fetchrow(
        """
        INSERT INTO apps (telegram_id, name, description, app_type, status)
        VALUES ($1, $2, $3, $4, 'queued')
        ON CONFLICT (telegram_id, name) DO UPDATE
            SET description = EXCLUDED.description,
                app_type    = EXCLUDED.app_type,
                status      = 'queued',
                error_detail = NULL,
                updated_at  = NOW()
        RETURNING id
        """,
        telegram_id,
        name,
        description,
        app_type,
    )
    return row["id"]


async def update_app_status(
    app_id: int,
    status: str,
    repo_url: str | None = None,
    app_url: str | None = None,
    error_detail: str | None = None,
) -> None:
    await _pool.execute(
        """
        UPDATE apps
        SET status       = $2,
            repo_url     = COALESCE($3, repo_url),
            app_url      = COALESCE($4, app_url),
            error_detail = COALESCE($5, error_detail),
            updated_at   = NOW()
        WHERE id = $1
        """,
        app_id,
        status,
        repo_url,
        app_url,
        error_detail,
    )


async def get_apps_for_user(telegram_id: int) -> list[dict]:
    rows = await _pool.fetch(
        """
        SELECT
            a.id, a.name, a.description, a.app_type,
            a.status, a.repo_url, a.app_url, a.error_detail,
            COUNT(ai.id) FILTER (WHERE ai.id IS NOT NULL) AS issue_count
        FROM apps a
        LEFT JOIN app_issues ai ON ai.app_id = a.id
        WHERE a.telegram_id = $1
          AND a.status != 'deleted'
        GROUP BY a.id
        ORDER BY a.created_at DESC
        """,
        telegram_id,
    )
    return [dict(r) for r in rows]


async def get_app_by_name(telegram_id: int, name: str) -> dict | None:
    row = await _pool.fetchrow(
        "SELECT * FROM apps WHERE telegram_id = $1 AND name = $2",
        telegram_id,
        name,
    )
    return dict(row) if row else None


async def soft_delete_app(telegram_id: int, name: str) -> None:
    await _pool.execute(
        """
        UPDATE apps SET status = 'deleted', updated_at = NOW()
        WHERE telegram_id = $1 AND name = $2
        """,
        telegram_id,
        name,
    )


async def get_app_issue(app_id: int, error_hash: str) -> str | None:
    """Returns the Gitea issue URL if this error hash is already known, else None."""
    row = await _pool.fetchrow(
        "SELECT gitea_issue_url FROM app_issues WHERE app_id = $1 AND error_hash = $2",
        app_id,
        error_hash,
    )
    return row["gitea_issue_url"] if row else None


async def insert_app_issue(
    app_id: int,
    error_hash: str,
    gitea_issue_url: str | None,
    is_breaking: bool,
) -> None:
    await _pool.execute(
        """
        INSERT INTO app_issues (app_id, error_hash, gitea_issue_url, is_breaking)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (app_id, error_hash) DO NOTHING
        """,
        app_id,
        error_hash,
        gitea_issue_url,
        is_breaking,
    )


async def count_open_issues(app_id: int) -> int:
    row = await _pool.fetchrow(
        "SELECT COUNT(*) AS n FROM app_issues WHERE app_id = $1", app_id
    )
    return row["n"] if row else 0
