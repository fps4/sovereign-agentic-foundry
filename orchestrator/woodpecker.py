"""Woodpecker CI repo activation.

When the coder pushes a new repo to Gitea, this module:
1. Upserts the org in Woodpecker's `orgs` table
2. Inserts the repo in Woodpecker's `repos` table with a generated hash
3. Generates the forge-hook JWT (HMAC-SHA256 signed with the repo hash)
4. Creates the Gitea webhook pointing at the Woodpecker hook endpoint

This mirrors what Woodpecker does internally via `POST /api/repos` but does not
require a valid Woodpecker API token — it works by writing directly to the shared
PostgreSQL instance and using the Gitea admin API.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time

import asyncpg
import httpx

WOODPECKER_DB_URL = os.getenv(
    "WOODPECKER_DB_URL",
    "postgresql://platform:changeme@postgres:5432/woodpecker",
)
WOODPECKER_HOOK_HOST = os.getenv("WOODPECKER_HOOK_HOST", "http://woodpecker-server:8000")
GITEA_URL = os.getenv("GITEA_URL", "http://gitea:3000")
GITEA_EXTERNAL_URL = os.getenv("GITEA_EXTERNAL_URL", "")
GITEA_ADMIN_USER = os.getenv("GITEA_ADMIN_USER", "platform")
GITEA_ADMIN_PASS = os.getenv("GITEA_ADMIN_PASS", "")

log = logging.getLogger("woodpecker")

_FORGE_ID = 1  # always 1 — only one Gitea forge is registered
_WOODPECKER_USER_ID = 1  # Woodpecker `platform` user id


def _make_repo_hash() -> str:
    """Generate a Woodpecker-style repo hash: base32(32 random bytes)."""
    return base64.b32encode(secrets.token_bytes(32)).decode()


def _make_hook_jwt(forge_id: int, repo_forge_remote_id: str, repo_hash: str) -> str:
    """Build a forge-hook JWT (HS256) signed with the repo hash."""
    header = base64.urlsafe_b64encode(
        json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode()
    ).rstrip(b"=").decode()

    payload = base64.urlsafe_b64encode(
        json.dumps({
            "forge-id": str(forge_id),
            "repo-forge-remote-id": str(repo_forge_remote_id),
            "type": "hook",
        }, separators=(",", ":")).encode()
    ).rstrip(b"=").decode()

    signing_input = f"{header}.{payload}".encode()
    sig = hmac.new(repo_hash.encode(), signing_input, hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(sig).rstrip(b"=").decode()
    return f"{header}.{payload}.{sig_b64}"


async def _get_gitea_repo_id(org: str, repo_name: str) -> str:
    """Return the Gitea repo ID (as a string) for the given org/repo."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{GITEA_URL}/api/v1/repos/{org}/{repo_name}",
            auth=(GITEA_ADMIN_USER, GITEA_ADMIN_PASS),
        )
        resp.raise_for_status()
        return str(resp.json()["id"])


async def _create_gitea_webhook(org: str, repo_name: str, hook_url: str) -> None:
    """Create a Gitea push webhook for the repo pointing at Woodpecker."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{GITEA_URL}/api/v1/repos/{org}/{repo_name}/hooks",
            auth=(GITEA_ADMIN_USER, GITEA_ADMIN_PASS),
        )
        if resp.status_code == 200:
            for hook in resp.json():
                if "woodpecker" in hook.get("config", {}).get("url", "") or \
                   "api/hook" in hook.get("config", {}).get("url", ""):
                    log.info("woodpecker.webhook_exists", extra={"org": org, "repo": repo_name})
                    return

        resp = await client.post(
            f"{GITEA_URL}/api/v1/repos/{org}/{repo_name}/hooks",
            auth=(GITEA_ADMIN_USER, GITEA_ADMIN_PASS),
            json={
                "type": "gitea",
                "active": True,
                "config": {
                    "content_type": "json",
                    "url": hook_url,
                },
                "events": ["push", "pull_request", "create"],
            },
        )
        resp.raise_for_status()
        log.info("woodpecker.webhook_created", extra={"org": org, "repo": repo_name, "url": hook_url})


async def activate_repo(org: str, repo_name: str) -> None:
    """Register a Gitea repo in Woodpecker CI and create the webhook."""
    try:
        gitea_repo_id = await _get_gitea_repo_id(org, repo_name)
    except httpx.HTTPError as exc:
        log.error("woodpecker.gitea_lookup_failed", extra={"org": org, "repo": repo_name, "error": str(exc)})
        return

    full_name = f"{org}/{repo_name}"
    gitea_ext = GITEA_EXTERNAL_URL or GITEA_URL
    clone_url = f"{gitea_ext}/{full_name}.git"
    forge_url = f"{gitea_ext}/{full_name}"

    repo_hash: str
    try:
        conn = await asyncpg.connect(WOODPECKER_DB_URL)
        try:
            # Upsert org
            org_row = await conn.fetchrow(
                "SELECT id FROM orgs WHERE forge_id = $1 AND name = $2",
                _FORGE_ID, org,
            )
            if org_row:
                org_id = org_row["id"]
            else:
                org_id = await conn.fetchval(
                    "INSERT INTO orgs (forge_id, name, is_user, private) "
                    "VALUES ($1, $2, false, true) RETURNING id",
                    _FORGE_ID, org,
                )
            log.info("woodpecker.org_ready", extra={"org": org, "org_id": org_id})

            # Upsert repo — get or create hash BEFORE building JWT
            existing = await conn.fetchrow(
                "SELECT id, hash FROM repos WHERE forge_id = $1 AND forge_remote_id = $2",
                _FORGE_ID, gitea_repo_id,
            )
            if existing:
                repo_hash = existing["hash"]
                log.info("woodpecker.repo_exists", extra={"full_name": full_name})
            else:
                repo_hash = _make_repo_hash()
                await conn.execute(
                    """
                    INSERT INTO repos (
                        user_id, forge_id, forge_remote_id, org_id,
                        owner, name, full_name,
                        forge_url, clone, clone_ssh,
                        branch, visibility, private, active,
                        hash, timeout,
                        pr_enabled, allow_pr, allow_deploy,
                        trusted, require_approval, approval_allowed_users,
                        cancel_previous_pipeline_events, netrc_trusted
                    ) VALUES (
                        $1, $2, $3, $4,
                        $5, $6, $7,
                        $8, $9, $10,
                        'main', 'private', true, true,
                        $11, 60,
                        true, true, false,
                        '{}', 'forks', '[]',
                        '[]', '[]'
                    )
                    """,
                    _WOODPECKER_USER_ID, _FORGE_ID, gitea_repo_id, org_id,
                    org, repo_name, full_name,
                    forge_url, clone_url, f"git@localhost:{full_name}.git",
                    repo_hash,
                )
                log.info("woodpecker.repo_inserted", extra={"full_name": full_name, "gitea_repo_id": gitea_repo_id})
        finally:
            await conn.close()
    except Exception as exc:
        log.error("woodpecker.db_error", extra={"full_name": full_name, "error": str(exc)})
        return

    # Build JWT AFTER repo_hash is known (existing or freshly generated)
    hook_jwt = _make_hook_jwt(_FORGE_ID, gitea_repo_id, repo_hash)
    hook_url = f"{WOODPECKER_HOOK_HOST}/api/hook?access_token={hook_jwt}"

    try:
        await _create_gitea_webhook(org, repo_name, hook_url)
    except httpx.HTTPError as exc:
        log.error("woodpecker.webhook_error", extra={"full_name": full_name, "error": str(exc)})
