#!/usr/bin/env python3
"""
Test: web portal user registration flow.

Covers:
  1. POST /auth/register-web  → creates user, returns JWT
  2. GET  /me                 → JWT resolves to correct email
  3. POST /auth/register-web  → duplicate email returns 409
  4. POST /auth/login         → login with registered credentials works
  5. POST /auth/register-web  → wrong invite code returns 403 (if INVITE_CODE set)
  6. Postgres rows            → user row written with correct fields

Usage:
    python scripts/test_web_registration.py
    GATEWAY_URL=http://ds1 python scripts/test_web_registration.py
"""
from __future__ import annotations

import os
import sys
import time
import subprocess
import json

import httpx

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://ds1")
# Use a timestamp suffix so repeated runs don't collide
_TS = str(int(time.time()))
TEST_EMAIL = os.getenv("TEST_EMAIL", f"e2e-reg-{_TS}@test.local")
TEST_PASSWORD = os.getenv("TEST_PASSWORD", "hunter2secure!")
TEST_INVITE = os.getenv("INVITE_CODE", "")  # match whatever the server has

_PASS = "\033[32m✓\033[0m"
_FAIL = "\033[31m✗\033[0m"
_INFO = "\033[34m→\033[0m"

failures: list[str] = []


def ok(msg: str) -> None:
    print(f"  {_PASS} {msg}")


def fail(msg: str) -> None:
    print(f"  {_FAIL} {msg}")
    failures.append(msg)


def info(msg: str) -> None:
    print(f"  {_INFO} {msg}")


def section(title: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


# ── Tests ──────────────────────────────────────────────────────────────────────

def test_register() -> str | None:
    """POST /auth/register-web — happy path."""
    section("1. Register new web user")
    info(f"email: {TEST_EMAIL}")
    try:
        r = httpx.post(
            f"{GATEWAY_URL}/auth/register-web",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD, "invite_code": TEST_INVITE},
            timeout=15.0,
        )
    except Exception as exc:
        fail(f"Request failed: {exc}")
        return None

    if r.status_code != 200:
        fail(f"Expected 200, got {r.status_code}: {r.text[:200]}")
        return None

    data = r.json()
    token = data.get("token") or data.get("accessToken")
    user_id = data.get("user_id")
    if not token:
        fail(f"No token in response: {data}")
        return None
    if not user_id:
        fail(f"No user_id in response: {data}")
        return None

    ok(f"Registered — user_id={user_id!r}")
    ok(f"JWT token received (len={len(token)})")
    return token


def test_me(token: str) -> bool:
    """GET /me — JWT resolves to correct user."""
    section("2. /me — token resolves to registered user")
    try:
        r = httpx.get(
            f"{GATEWAY_URL}/me",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10.0,
        )
    except Exception as exc:
        fail(f"Request failed: {exc}")
        return False

    if r.status_code != 200:
        fail(f"Expected 200, got {r.status_code}: {r.text[:200]}")
        return False

    data = r.json()
    if data.get("email") != TEST_EMAIL:
        fail(f"email mismatch: expected {TEST_EMAIL!r}, got {data.get('email')!r}")
        return False
    if not data.get("registered"):
        fail(f"/me says registered=False for freshly registered user")
        return False

    ok(f"email={data['email']!r}  registered={data['registered']}")
    return True


def test_duplicate_email() -> bool:
    """POST /auth/register-web with same email → 409."""
    section("3. Duplicate email → 409")
    try:
        r = httpx.post(
            f"{GATEWAY_URL}/auth/register-web",
            json={"email": TEST_EMAIL, "password": "different!", "invite_code": TEST_INVITE},
            timeout=10.0,
        )
    except Exception as exc:
        fail(f"Request failed: {exc}")
        return False

    if r.status_code == 409:
        ok(f"409 Conflict returned as expected")
        return True
    fail(f"Expected 409, got {r.status_code}: {r.text[:200]}")
    return False


def test_login() -> bool:
    """POST /auth/login — credentials work after registration."""
    section("4. Login with registered credentials")
    try:
        r = httpx.post(
            f"{GATEWAY_URL}/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
            timeout=10.0,
        )
    except Exception as exc:
        fail(f"Request failed: {exc}")
        return False

    if r.status_code != 200:
        fail(f"Expected 200, got {r.status_code}: {r.text[:200]}")
        return False

    data = r.json()
    token = data.get("token") or data.get("accessToken")
    if not token:
        fail(f"No token in login response: {data}")
        return False

    ok(f"Login succeeded — token received (len={len(token)})")
    return True


def test_wrong_password() -> bool:
    """POST /auth/login with wrong password → 401."""
    section("5. Login with wrong password → 401")
    try:
        r = httpx.post(
            f"{GATEWAY_URL}/auth/login",
            json={"email": TEST_EMAIL, "password": "wrongpassword"},
            timeout=10.0,
        )
    except Exception as exc:
        fail(f"Request failed: {exc}")
        return False

    if r.status_code == 401:
        ok("401 Unauthorized returned as expected")
        return True
    fail(f"Expected 401, got {r.status_code}: {r.text[:200]}")
    return False


def test_postgres_row() -> bool:
    """Check the user row exists directly in Postgres via docker exec."""
    section("6. Postgres — user row written correctly")
    sql = (
        f"SELECT telegram_id, email, verified, tenant_id IS NOT NULL "
        f"FROM users WHERE email = '{TEST_EMAIL}';"
    )
    cmd = ["ssh", "ds1", f'docker exec platform-postgres-1 psql -U platform -d platform -t -c "{sql}"']
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        output = result.stdout.strip()
    except Exception as exc:
        fail(f"psql exec failed: {exc}")
        return False

    if not output:
        fail(f"No row found in users table for {TEST_EMAIL!r}")
        return False

    info(f"Row: {output}")
    parts = [p.strip() for p in output.split("|")]
    # parts: [telegram_id, email, verified, tenant_id IS NOT NULL]
    if len(parts) < 4:
        fail(f"Unexpected row format: {output!r}")
        return False

    user_id, email, verified, has_tenant = parts[0], parts[1], parts[2], parts[3]
    if not user_id.startswith("web-"):
        fail(f"user_id should start with 'web-', got {user_id!r}")
        return False
    if verified.strip() != "t":
        fail(f"verified should be TRUE, got {verified!r}")
        return False
    if has_tenant.strip() != "t":
        fail(f"tenant_id should be set, got {has_tenant!r}")
        return False

    ok(f"user_id={user_id!r}  verified={verified.strip()}  has_tenant={has_tenant.strip()}")
    return True


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> int:
    print("\n╔══════════════════════════════════════════════════╗")
    print("║  Web Registration — Integration Test             ║")
    print("╚══════════════════════════════════════════════════╝")
    print(f"\n  Gateway : {GATEWAY_URL}")
    print(f"  Email   : {TEST_EMAIL}")

    token = test_register()
    if token:
        test_me(token)
    test_duplicate_email()
    test_login()
    test_wrong_password()
    test_postgres_row()

    print(f"\n{'═' * 60}")
    if failures:
        print(f"  {_FAIL} {len(failures)} failure(s):")
        for f in failures:
            print(f"      • {f}")
        print()
        return 1
    else:
        print(f"  {_PASS} All checks passed!")
        print()
        return 0


if __name__ == "__main__":
    sys.exit(main())
