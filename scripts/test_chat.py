#!/usr/bin/env python3
"""
Test: portal chat flow — end-to-end from registration through multi-turn conversation.

Covers:
  1. Register a new web user (or re-use via login)
  2. POST /chat — first turn, expect a reply
  3. POST /chat — second turn with history, expect a follow-up reply
  4. Intake agent /chat — direct call (bypass gateway auth)
  5. Ollama reachability — GET /api/tags inside the intake container

Usage:
    python scripts/test_chat.py
    GATEWAY_URL=http://ds1 python scripts/test_chat.py
    GATEWAY_URL=http://ds1 INVITE_CODE=674523 python scripts/test_chat.py
"""
from __future__ import annotations

import os
import sys
import time
import subprocess

import httpx

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://ds1")
INTAKE_URL = os.getenv("INTAKE_URL", "")          # optional: direct intake URL
INVITE_CODE = os.getenv("INVITE_CODE", "")
_TS = str(int(time.time()))
TEST_EMAIL = os.getenv("TEST_EMAIL", f"chattest-{_TS}@test.local")
TEST_PASSWORD = os.getenv("TEST_PASSWORD", "Hunter2secure1!")

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


# ── Helpers ─────────────────────────────────────────────────────────────────────

def _get_token() -> str | None:
    """Register a fresh user and return a JWT."""
    try:
        r = httpx.post(
            f"{GATEWAY_URL}/auth/register-web",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD, "invite_code": INVITE_CODE},
            timeout=15.0,
        )
    except Exception as exc:
        fail(f"register request failed: {exc}")
        return None

    if r.status_code == 200:
        token = r.json().get("token") or r.json().get("accessToken")
        ok(f"Registered as {TEST_EMAIL!r}")
        return token

    if r.status_code == 409:
        # Already exists — log in instead
        info("Email already exists, falling back to login")
        try:
            r2 = httpx.post(
                f"{GATEWAY_URL}/auth/login",
                json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
                timeout=15.0,
            )
        except Exception as exc:
            fail(f"login request failed: {exc}")
            return None
        if r2.status_code == 200:
            token = r2.json().get("token") or r2.json().get("accessToken")
            ok(f"Logged in as {TEST_EMAIL!r}")
            return token
        fail(f"Login failed: {r2.status_code} {r2.text[:200]}")
        return None

    fail(f"Registration failed: {r.status_code} {r.text[:200]}")
    return None


# ── Tests ────────────────────────────────────────────────────────────────────────

def test_first_turn(token: str) -> list[dict] | None:
    """POST /chat — first user message, must return a text reply."""
    section("1. First chat turn")
    message = "I want to build a task tracker for my team"
    info(f"Sending: {message!r}")
    try:
        r = httpx.post(
            f"{GATEWAY_URL}/chat",
            headers={"Authorization": f"Bearer {token}"},
            json={"message": message, "history": []},
            timeout=120.0,
        )
    except Exception as exc:
        fail(f"Request failed: {exc}")
        return None

    if r.status_code != 200:
        fail(f"Expected 200, got {r.status_code}: {r.text[:400]}")
        return None

    data = r.json()
    reply = data.get("reply", "")
    if not reply:
        fail(f"No 'reply' field in response: {data}")
        return None

    ok(f"Reply received ({len(reply)} chars)")
    info(f"Reply: {reply[:120]}{'…' if len(reply) > 120 else ''}")

    spec_locked = data.get("spec_locked", False)
    info(f"spec_locked={spec_locked}")

    return [
        {"role": "user", "content": message},
        {"role": "assistant", "content": reply},
    ]


def test_second_turn(token: str, history: list[dict]) -> bool:
    """POST /chat — follow-up message with history."""
    section("2. Second chat turn (with history)")
    message = "It should track bugs and feature requests, with priorities"
    info(f"Sending: {message!r}")
    try:
        r = httpx.post(
            f"{GATEWAY_URL}/chat",
            headers={"Authorization": f"Bearer {token}"},
            json={"message": message, "history": history},
            timeout=120.0,
        )
    except Exception as exc:
        fail(f"Request failed: {exc}")
        return False

    if r.status_code != 200:
        fail(f"Expected 200, got {r.status_code}: {r.text[:400]}")
        return False

    data = r.json()
    reply = data.get("reply", "")
    if not reply:
        fail(f"No 'reply' field in response: {data}")
        return False

    ok(f"Reply received ({len(reply)} chars)")
    info(f"Reply: {reply[:120]}{'…' if len(reply) > 120 else ''}")
    return True


def test_unauthenticated_chat() -> bool:
    """POST /chat without token → 401 or 403."""
    section("3. Unauthenticated chat → 401/403")
    try:
        r = httpx.post(
            f"{GATEWAY_URL}/chat",
            json={"message": "hello", "history": []},
            timeout=10.0,
        )
    except Exception as exc:
        fail(f"Request failed: {exc}")
        return False

    if r.status_code in (401, 403):
        ok(f"{r.status_code} returned as expected")
        return True
    fail(f"Expected 401/403, got {r.status_code}: {r.text[:200]}")
    return False


def test_intake_direct() -> bool:
    """Call intake /chat directly (if INTAKE_URL is set)."""
    section("4. Intake agent direct call")
    url = INTAKE_URL
    if not url:
        # Try to derive via docker exec
        info("INTAKE_URL not set — probing via SSH")
        try:
            result = subprocess.run(
                ["ssh", "ds1", "curl -sf http://localhost:8001/health"],
                capture_output=True, text=True, timeout=10,
            )
            if '"ok"' in result.stdout or "ok" in result.stdout:
                url = "http://ds1:8001"
                info(f"Intake reachable at {url}")
            else:
                info("Intake not directly reachable from outside — skipping direct test")
                ok("Skipped (intake not exposed externally)")
                return True
        except Exception as exc:
            info(f"SSH probe failed: {exc} — skipping")
            ok("Skipped")
            return True

    try:
        r = httpx.post(
            f"{url}/chat",
            json={"message": "I want to build a simple CRUD app", "history": []},
            timeout=120.0,
        )
    except Exception as exc:
        fail(f"Request failed: {exc}")
        return False

    if r.status_code != 200:
        fail(f"Expected 200, got {r.status_code}: {r.text[:400]}")
        return False

    data = r.json()
    if not data.get("reply"):
        fail(f"No 'reply' in response: {data}")
        return False

    ok(f"Intake replied directly ({len(data['reply'])} chars)")
    return True


def test_ollama_models() -> bool:
    """Check that at least one model is loaded in Ollama."""
    section("5. Ollama — model availability")
    cmd = ["ssh", "ds1", "docker exec platform-ollama-1 ollama list"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        output = result.stdout.strip()
    except Exception as exc:
        fail(f"ollama list failed: {exc}")
        return False

    lines = [l for l in output.splitlines() if l.strip() and "NAME" not in l]
    if not lines:
        fail("No models found in Ollama — run: DOCKER_HOST=ssh://ds1 bash scripts/pull_models.sh")
        return False

    for line in lines:
        ok(f"Model available: {line.split()[0]}")
    return True


# ── Main ────────────────────────────────────────────────────────────────────────

def main() -> int:
    print("\n╔══════════════════════════════════════════════════╗")
    print("║  Portal Chat — Integration Test                  ║")
    print("╚══════════════════════════════════════════════════╝")
    print(f"\n  Gateway : {GATEWAY_URL}")
    print(f"  Email   : {TEST_EMAIL}")

    # Prerequisite checks
    test_ollama_models()
    test_unauthenticated_chat()

    # Auth + chat flow
    token = _get_token()
    if not token:
        print(f"\n{'═' * 60}")
        print(f"  {_FAIL} Cannot obtain token — aborting chat tests")
        print()
        return 1

    history = test_first_turn(token)
    if history:
        test_second_turn(token, history)

    test_intake_direct()

    print(f"\n{'═' * 60}")
    if failures:
        print(f"  {_FAIL} {len(failures)} failure(s):")
        for f in failures:
            print(f"      • {f}")
        print()
        return 1

    print(f"  {_PASS} All checks passed!")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
