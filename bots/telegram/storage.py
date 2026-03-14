"""Persistent FSM storage backed by PostgreSQL.

Stores FSM state and data in a single `fsm_state` table so in-progress
flows survive bot container restarts.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

import asyncpg
from aiogram.fsm.storage.base import BaseStorage, StorageKey, StateType


class PostgresStorage(BaseStorage):
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @classmethod
    async def create(cls, dsn: str) -> "PostgresStorage":
        pool = await asyncpg.create_pool(dsn)
        storage = cls(pool)
        await storage._init()
        return storage

    async def _init(self) -> None:
        await self._pool.execute("""
            CREATE TABLE IF NOT EXISTS fsm_state (
                key   TEXT PRIMARY KEY,
                state TEXT,
                data  JSONB NOT NULL DEFAULT '{}'
            )
        """)

    @staticmethod
    def _key(key: StorageKey) -> str:
        return f"{key.bot_id}:{key.chat_id}:{key.user_id}:{key.destiny}"

    async def set_state(self, key: StorageKey, state: StateType = None) -> None:
        await self._pool.execute(
            """
            INSERT INTO fsm_state (key, state) VALUES ($1, $2)
            ON CONFLICT (key) DO UPDATE SET state = EXCLUDED.state
            """,
            self._key(key),
            state.state if state else None,
        )

    async def get_state(self, key: StorageKey) -> Optional[str]:
        row = await self._pool.fetchrow(
            "SELECT state FROM fsm_state WHERE key = $1", self._key(key)
        )
        return row["state"] if row else None

    async def set_data(self, key: StorageKey, data: Dict[str, Any]) -> None:
        await self._pool.execute(
            """
            INSERT INTO fsm_state (key, data) VALUES ($1, $2::jsonb)
            ON CONFLICT (key) DO UPDATE SET data = EXCLUDED.data
            """,
            self._key(key),
            json.dumps(data),
        )

    async def get_data(self, key: StorageKey) -> Dict[str, Any]:
        row = await self._pool.fetchrow(
            "SELECT data FROM fsm_state WHERE key = $1", self._key(key)
        )
        if row and row["data"]:
            return dict(row["data"])
        return {}

    async def close(self) -> None:
        await self._pool.close()
