"""Gitea API client.

Creates a repository and commits files using the Gitea REST API.
If an org is provided repos are created under that org; otherwise under the admin user.
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


async def create_repo_with_files(
    name: str, description: str, files: list[dict], org: str = ""
) -> str:
    """Create a Gitea repo under `org` (or admin user if blank), commit all files."""
    owner = org if org else GITEA_ADMIN_USER
    create_url = (
        f"/api/v1/orgs/{org}/repos" if org else "/api/v1/user/repos"
    )

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
        if resp.status_code == 409:
            raise RuntimeError(
                f"Repository '{name}' already exists. "
                "Choose a different name or delete the existing repo."
            )
        resp.raise_for_status()
        repo = resp.json()

        for f in files:
            content_b64 = base64.b64encode(f["content"].encode()).decode()
            file_resp = await client.post(
                f"/api/v1/repos/{owner}/{name}/contents/{f['path']}",
                json={
                    "message": f"chore: scaffold {f['path']}",
                    "content": content_b64,
                    "branch": "main",
                },
            )
            file_resp.raise_for_status()

        return repo["html_url"]
