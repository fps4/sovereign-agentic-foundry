"""Gitea API client.

Creates or updates a repository and commits files using the Gitea REST API.
If an org is provided repos are created under that org; otherwise under the admin user.
If the repo already exists (created by the designer agent) files are upserted.
"""

from __future__ import annotations

import base64
import os

import httpx

GITEA_URL = os.getenv("GITEA_URL", "http://gitea:3000")
GITEA_ADMIN_USER = os.getenv("GITEA_ADMIN_USER", "platform")
GITEA_ADMIN_PASS = os.getenv("GITEA_ADMIN_PASS", "")


def _auth() -> httpx.BasicAuth:
    if not GITEA_ADMIN_PASS:
        raise RuntimeError(
            "GITEA_ADMIN_PASS is not set. Add it to .env and redeploy."
        )
    return httpx.BasicAuth(GITEA_ADMIN_USER, GITEA_ADMIN_PASS)


async def _upsert_file(client: httpx.AsyncClient, owner: str, repo: str, f: dict) -> None:
    """Create a file, or update it if it already exists."""
    path = f["path"]
    content_b64 = base64.b64encode(f["content"].encode()).decode()
    resp = await client.post(
        f"/api/v1/repos/{owner}/{repo}/contents/{path}",
        json={"message": f"feat: add {path}", "content": content_b64, "branch": "main"},
    )
    if resp.status_code == 422:
        # File exists — fetch its SHA and update
        get_resp = await client.get(f"/api/v1/repos/{owner}/{repo}/contents/{path}")
        get_resp.raise_for_status()
        sha = get_resp.json()["sha"]
        put_resp = await client.put(
            f"/api/v1/repos/{owner}/{repo}/contents/{path}",
            json={
                "message": f"feat: update {path}",
                "content": content_b64,
                "sha": sha,
                "branch": "main",
            },
        )
        put_resp.raise_for_status()
    else:
        resp.raise_for_status()


async def create_repo_with_files(
    name: str, description: str, files: list[dict], org: str = ""
) -> str:
    """Create a Gitea repo (or reuse if it already exists) and commit all files."""
    owner = org if org else GITEA_ADMIN_USER
    create_url = f"/api/v1/orgs/{org}/repos" if org else "/api/v1/user/repos"

    async with httpx.AsyncClient(
        base_url=GITEA_URL, auth=_auth(), timeout=30.0
    ) as client:
        resp = await client.post(
            create_url,
            json={
                "name": name,
                "description": description,
                "private": False,
                "auto_init": False,
                "default_branch": "main",
            },
        )
        if resp.status_code not in (201, 409):
            resp.raise_for_status()

        for f in files:
            await _upsert_file(client, owner, name, f)

        return f"{GITEA_URL}/{owner}/{name}"
