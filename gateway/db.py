"""Postgres connection pool and schema for the platform database."""
from __future__ import annotations

import os

import asyncpg

DB_URL = os.getenv("DB_URL", "postgresql://platform:changeme@postgres:5432/platform")

_pool: asyncpg.Pool | None = None


async def init_pool() -> None:
    global _pool
    _pool = await asyncpg.create_pool(DB_URL)
    await _migrate()


async def close_pool() -> None:
    if _pool:
        await _pool.close()


async def _migrate() -> None:
    await _pool.execute("""
        CREATE TABLE IF NOT EXISTS tenants (
            id          SERIAL PRIMARY KEY,
            tenant_type TEXT NOT NULL DEFAULT 'single_user',
            gitea_org   TEXT NOT NULL,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    await _pool.execute("""
        CREATE TABLE IF NOT EXISTS users (
            telegram_id       TEXT PRIMARY KEY,
            telegram_username TEXT,
            email             TEXT UNIQUE,
            password_hash     TEXT,
            tenant_id         INTEGER REFERENCES tenants(id),
            verified          BOOLEAN NOT NULL DEFAULT FALSE,
            verification_code TEXT,
            design_mode       BOOLEAN NOT NULL DEFAULT FALSE,
            created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    await _pool.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id         SERIAL PRIMARY KEY,
            user_id    TEXT NOT NULL REFERENCES users(telegram_id),
            role       TEXT NOT NULL,
            content    TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    await _pool.execute("""
        CREATE TABLE IF NOT EXISTS apps (
            id                  SERIAL PRIMARY KEY,
            tenant_id           INTEGER NOT NULL REFERENCES tenants(id),
            created_by_user_id  TEXT NOT NULL REFERENCES users(telegram_id),
            name                TEXT NOT NULL,
            description         TEXT NOT NULL DEFAULT '',
            app_type            TEXT NOT NULL DEFAULT '',
            status              TEXT NOT NULL DEFAULT 'queued',
            repo_url            TEXT,
            app_url             TEXT,
            error_detail        TEXT,
            archived            BOOLEAN NOT NULL DEFAULT FALSE,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (tenant_id, name)
        )
    """)
    await _pool.execute("""
        CREATE TABLE IF NOT EXISTS app_issues (
            id              SERIAL PRIMARY KEY,
            app_id          INTEGER NOT NULL REFERENCES apps(id),
            error_hash      TEXT NOT NULL,
            gitea_issue_url TEXT,
            is_breaking     BOOLEAN NOT NULL DEFAULT FALSE,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (app_id, error_hash)
        )
    """)
    await _pool.execute("""
        CREATE TABLE IF NOT EXISTS agent_runs (
            id         BIGSERIAL PRIMARY KEY,
            run_id     TEXT NOT NULL,
            agent      TEXT NOT NULL,
            repo       TEXT,
            task_ref   TEXT,
            event      TEXT NOT NULL,
            status     TEXT NOT NULL DEFAULT 'ok',
            payload    JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    await _pool.execute(
        "CREATE INDEX IF NOT EXISTS agent_runs_run_id ON agent_runs (run_id)"
    )
    await _pool.execute(
        "CREATE INDEX IF NOT EXISTS agent_runs_repo ON agent_runs (repo, created_at DESC)"
    )
    await _pool.execute("""
        CREATE TABLE IF NOT EXISTS board_cards (
            id          SERIAL PRIMARY KEY,
            app_id      INTEGER NOT NULL REFERENCES apps(id),
            title       TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            list        TEXT NOT NULL DEFAULT 'backlog',
            position    INTEGER NOT NULL DEFAULT 0,
            created_by  TEXT NOT NULL DEFAULT 'user',
            locked      BOOLEAN NOT NULL DEFAULT FALSE,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)


# ── Tenants ────────────────────────────────────────────────────────────────────

async def create_tenant(gitea_org: str) -> int:
    row = await _pool.fetchrow(
        """
        INSERT INTO tenants (gitea_org) VALUES ($1) RETURNING id
        """,
        gitea_org,
    )
    return row["id"]


async def get_tenant(tenant_id: int) -> dict | None:
    row = await _pool.fetchrow("SELECT * FROM tenants WHERE id = $1", tenant_id)
    return dict(row) if row else None


# ── Users ──────────────────────────────────────────────────────────────────────

async def get_user(telegram_id: str | int) -> dict | None:
    row = await _pool.fetchrow(
        "SELECT * FROM users WHERE telegram_id = $1", str(telegram_id)
    )
    return dict(row) if row else None


async def get_user_by_email(email: str) -> dict | None:
    row = await _pool.fetchrow("SELECT * FROM users WHERE email = $1", email)
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
                verified          = FALSE
        """,
        str(telegram_id),
        telegram_username,
        code,
    )


async def verify_user(telegram_id: int, tenant_id: int) -> None:
    await _pool.execute(
        """
        UPDATE users
        SET verified          = TRUE,
            tenant_id         = $2,
            verification_code = NULL
        WHERE telegram_id = $1
        """,
        str(telegram_id),
        tenant_id,
    )


async def create_web_user(
    email: str, password_hash: str, tenant_id: int
) -> str:
    """Register a web-only user (no Telegram). Returns the synthetic user_id."""
    user_id = f"web-{email}"
    await _pool.execute(
        """
        INSERT INTO users (telegram_id, email, password_hash, tenant_id, verified)
        VALUES ($1, $2, $3, $4, TRUE)
        ON CONFLICT (telegram_id) DO NOTHING
        """,
        user_id,
        email,
        password_hash,
        tenant_id,
    )
    return user_id


# ── Messages ───────────────────────────────────────────────────────────────────

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


# ── Apps ───────────────────────────────────────────────────────────────────────

async def register_app(
    tenant_id: int, created_by_user_id: str, name: str, description: str, app_type: str
) -> int:
    row = await _pool.fetchrow(
        """
        INSERT INTO apps (tenant_id, created_by_user_id, name, description, app_type, status)
        VALUES ($1, $2, $3, $4, $5, 'queued')
        ON CONFLICT (tenant_id, name) DO UPDATE
            SET description        = EXCLUDED.description,
                app_type           = EXCLUDED.app_type,
                status             = 'queued',
                error_detail       = NULL,
                archived           = FALSE,
                updated_at         = NOW()
        RETURNING id
        """,
        tenant_id,
        created_by_user_id,
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


async def get_apps_for_tenant(tenant_id: int) -> list[dict]:
    rows = await _pool.fetch(
        """
        SELECT
            a.id, a.name, a.description, a.app_type,
            a.status, a.repo_url, a.app_url, a.error_detail,
            a.created_at, a.updated_at,
            COUNT(ai.id) FILTER (WHERE ai.id IS NOT NULL) AS issue_count
        FROM apps a
        LEFT JOIN app_issues ai ON ai.app_id = a.id
        WHERE a.tenant_id = $1
          AND a.archived  = FALSE
        GROUP BY a.id
        ORDER BY a.created_at DESC
        """,
        tenant_id,
    )
    return [dict(r) for r in rows]


async def get_app_by_name(tenant_id: int, name: str) -> dict | None:
    row = await _pool.fetchrow(
        "SELECT * FROM apps WHERE tenant_id = $1 AND name = $2 AND archived = FALSE",
        tenant_id,
        name,
    )
    return dict(row) if row else None


async def archive_app(app_id: int) -> None:
    await _pool.execute(
        "UPDATE apps SET archived = TRUE, updated_at = NOW() WHERE id = $1",
        app_id,
    )


# ── App issues ─────────────────────────────────────────────────────────────────

async def get_app_issue(app_id: int, error_hash: str) -> str | None:
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


# ── Agent runs ─────────────────────────────────────────────────────────────────

async def log_run_step(
    run_id: str,
    agent: str,
    event: str,
    repo: str | None = None,
    task_ref: str | None = None,
    status: str = "ok",
    payload: dict | None = None,
) -> None:
    import json as _json
    await _pool.execute(
        """
        INSERT INTO agent_runs (run_id, agent, repo, task_ref, event, status, payload)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        """,
        run_id,
        agent,
        repo,
        task_ref,
        event,
        status,
        _json.dumps(payload) if payload else None,
    )


async def get_run_steps(
    repo: str | None = None,
    run_id: str | None = None,
    limit: int = 100,
) -> list[dict]:
    if run_id:
        rows = await _pool.fetch(
            "SELECT * FROM agent_runs WHERE run_id = $1 ORDER BY created_at LIMIT $2",
            run_id,
            limit,
        )
    elif repo:
        rows = await _pool.fetch(
            "SELECT * FROM agent_runs WHERE repo = $1 ORDER BY created_at DESC LIMIT $2",
            repo,
            limit,
        )
    else:
        rows = await _pool.fetch(
            "SELECT * FROM agent_runs ORDER BY created_at DESC LIMIT $1", limit
        )
    return [dict(r) for r in rows]
