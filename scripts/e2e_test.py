#!/usr/bin/env python3
"""End-to-end test: user request → clarify & design → code → test → report back → working URL.

Usage:
    python scripts/e2e_test.py

Environment variables (all optional — defaults match local docker compose):
    ORCHESTRATOR_URL   e.g. http://ds1 (via Traefik) or http://localhost:8000
    GITEA_URL          e.g. http://ds1:3000
    TEST_TELEGRAM_ID   fake Telegram user ID to use for the test (default: 9999000001)
    SKIP_HEALTH        set to 1 to skip agent health checks
"""
from __future__ import annotations

import os
import sys
import time
import uuid

import httpx

ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "http://localhost:8000")
GITEA_URL = os.getenv("GITEA_URL", "http://localhost:3000")
TEST_TELEGRAM_ID = int(os.getenv("TEST_TELEGRAM_ID", "9999000001"))
SKIP_HEALTH = os.getenv("SKIP_HEALTH", "") == "1"

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


# ── Helpers ────────────────────────────────────────────────────────────────────

def get(path: str, **params) -> httpx.Response:
    return httpx.get(f"{ORCHESTRATOR_URL}{path}", params=params, timeout=15.0)


def post(path: str, **body) -> httpx.Response:
    return httpx.post(f"{ORCHESTRATOR_URL}{path}", json=body, timeout=120.0)


# ── Tests ──────────────────────────────────────────────────────────────────────

def test_health() -> None:
    section("1. Service health checks")
    for name, url in [
        ("orchestrator", f"{ORCHESTRATOR_URL}/health"),
        ("coder", f"{ORCHESTRATOR_URL.replace(':8000', '')}:8001/health"),
        ("designer", f"{ORCHESTRATOR_URL.replace(':8000', '')}:8003/health"),
        ("tester", f"{ORCHESTRATOR_URL.replace(':8000', '')}:8002/health"),
    ]:
        if SKIP_HEALTH and name != "orchestrator":
            info(f"Skipping {name} (SKIP_HEALTH=1)")
            continue
        try:
            r = httpx.get(url, timeout=5.0)
            if r.status_code == 200 and r.json().get("status") == "ok":
                ok(f"{name} healthy")
            else:
                fail(f"{name} unhealthy: {r.status_code} {r.text[:80]}")
        except Exception as exc:
            fail(f"{name} unreachable: {exc}")


def test_registration() -> tuple[bool, int]:
    """Register (or re-use) a test user. Returns (success, telegram_id)."""
    section("2. User registration")
    tid = TEST_TELEGRAM_ID
    username = f"e2e_test_{tid}"

    # Check if already registered
    try:
        r = get("/me", telegram_id=tid)
        if r.json().get("registered"):
            ok(f"User {tid} already registered — reusing")
            return True, tid
    except Exception:
        pass

    # Register
    try:
        r = post("/register", telegram_id=tid, telegram_username=username)
        r.raise_for_status()
        data = r.json()
    except Exception as exc:
        fail(f"Register failed: {exc}")
        return False, tid

    if data["message"] == "already_registered":
        ok("Already registered")
        return True, tid

    # Verify with the server-issued code
    code = data["code"]
    try:
        r = post("/verify", telegram_id=tid, code=code)
        r.raise_for_status()
        result = r.json()
    except Exception as exc:
        fail(f"Verify failed: {exc}")
        return False, tid

    if result["success"]:
        ok(f"Registered and verified user {tid}")
        return True, tid
    else:
        fail(f"Verification failed: {result['message']}")
        return False, tid


def test_designer_clarification(tid: int) -> bool:
    """Send a vague build request and confirm designer asks a clarifying question."""
    section("3. Designer — clarification turn")
    user_id = str(tid)
    # Vague request that should trigger clarification
    msg = "I need something to manage patient records"
    info(f"Sending: {msg!r}")
    try:
        r = post("/chat", user_id=user_id, message=msg)
        r.raise_for_status()
        reply = r.json()["reply"]
    except Exception as exc:
        fail(f"Chat request failed: {exc}")
        return False

    info(f"Reply: {reply[:120]!r}")
    if "?" in reply or any(kw in reply.lower() for kw in ("what", "which", "how", "could", "would", "describe")):
        ok("Designer responded with a clarifying question")
        return True
    else:
        fail(f"Expected a clarifying question, got: {reply[:120]!r}")
        return False


def test_designer_completion(tid: int) -> tuple[bool, str]:
    """Provide enough information for the designer to produce a spec and kick off build."""
    section("4. Designer — spec ready & build triggered")
    user_id = str(tid)
    app_name = f"e2e-patient-records-{uuid.uuid4().hex[:6]}"

    # Give enough info to satisfy the designer
    msg = (
        f"Build a form app called {app_name}. "
        "It should collect patient name, email, date of birth, and chief complaint. "
        "Use Python FastAPI. Keep it simple."
    )
    info(f"Sending: {msg[:80]!r}...")
    try:
        r = post("/chat", user_id=user_id, message=msg)
        r.raise_for_status()
        reply = r.json()["reply"]
    except Exception as exc:
        fail(f"Chat request failed: {exc}")
        return False, ""

    info(f"Reply: {reply[:150]!r}")

    # The designer may still ask one more question, or may say ready
    if "ready" in reply.lower() or "setting up" in reply.lower() or "creating" in reply.lower() or "scaffold" in reply.lower():
        ok("Designer confirmed spec ready and build started")
        return True, app_name

    # Try one more clarifying answer
    info("Designer asked another question — answering...")
    try:
        r = post("/chat", user_id=user_id, message="Python FastAPI, SQLite database, no auth needed")
        r.raise_for_status()
        reply = r.json()["reply"]
    except Exception as exc:
        fail(f"Follow-up chat failed: {exc}")
        return False, ""

    info(f"Reply: {reply[:150]!r}")
    if "?" not in reply or any(kw in reply.lower() for kw in ("building", "ready", "setting", "scaffold", "creating")):
        ok("Designer completed spec after clarification")
        return True, app_name

    fail(f"Designer still asking questions after 2 clarifications: {reply[:120]!r}")
    return False, app_name


def test_app_build(tid: int, app_name: str, timeout: int = 300) -> bool:
    """Poll app registry until the app moves to 'active' or 'failed'."""
    section("5. Build pipeline — waiting for app to go active")
    info(f"Polling /apps for {app_name!r} (timeout={timeout}s)...")
    deadline = time.time() + timeout
    last_status = "unknown"

    while time.time() < deadline:
        try:
            r = get("/apps", telegram_id=tid)
            r.raise_for_status()
            apps = r.json()
        except Exception as exc:
            info(f"  /apps poll error: {exc}")
            time.sleep(10)
            continue

        matched = next((a for a in apps if a["name"] == app_name), None)
        if not matched:
            time.sleep(10)
            continue

        status = matched["status"]
        if status != last_status:
            info(f"  status → {status}")
            last_status = status

        if status == "active":
            ok(f"App {app_name!r} is active")
            app_url = matched.get("url") or ""
            if app_url:
                info(f"  URL: {app_url}")
            return True
        if status == "failed":
            fail(f"App {app_name!r} build failed: {matched.get('error_detail', 'unknown')[:120]}")
            return False

        time.sleep(10)

    fail(f"App {app_name!r} did not reach 'active' within {timeout}s (last status: {last_status})")
    return False


def test_app_url(tid: int, app_name: str) -> bool:
    """Verify the live app URL responds to /health."""
    section("6. Live app — HTTP health check")
    try:
        r = get("/apps", telegram_id=tid)
        r.raise_for_status()
        apps = r.json()
    except Exception as exc:
        fail(f"Could not fetch app list: {exc}")
        return False

    matched = next((a for a in apps if a["name"] == app_name), None)
    if not matched:
        fail(f"App {app_name!r} not found in /apps")
        return False

    app_url = matched.get("url")
    if not app_url:
        fail(f"App {app_name!r} has no URL")
        return False

    info(f"Checking {app_url}/health ...")
    try:
        r = httpx.get(f"{app_url}/health", timeout=10.0)
        if r.status_code == 200:
            ok(f"App responds at {app_url}/health → {r.json()}")
            return True
        else:
            fail(f"App health returned {r.status_code}: {r.text[:80]}")
            return False
    except Exception as exc:
        fail(f"App URL unreachable: {exc}")
        return False


def test_run_logs(app_name: str) -> bool:
    """Verify agent run events were recorded for this build."""
    section("7. Agent run log — pipeline trace")
    try:
        r = get("/runs", repo=app_name)
        r.raise_for_status()
        steps = r.json()
    except Exception as exc:
        fail(f"Could not fetch run steps: {exc}")
        return False

    if not steps:
        fail(f"No run steps recorded for {app_name!r}")
        return False

    agents_seen = {s["agent"] for s in steps}
    events_seen = {s["event"] for s in steps}
    info(f"Agents in trace: {sorted(agents_seen)}")
    info(f"Events in trace: {sorted(events_seen)}")

    expected_agents = {"orchestrator", "designer", "coder"}
    missing = expected_agents - agents_seen
    if missing:
        fail(f"Missing agents in trace: {missing}")
        return False

    ok(f"Pipeline trace complete — {len(steps)} step(s) from {sorted(agents_seen)}")
    return True


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> int:
    print("\n╔══════════════════════════════════════════════════╗")
    print("║  Sovereign Agentic Foundry — End-to-End Test     ║")
    print("╚══════════════════════════════════════════════════╝")
    print(f"\n  Orchestrator : {ORCHESTRATOR_URL}")
    print(f"  Test user ID : {TEST_TELEGRAM_ID}")

    test_health()

    ok_reg, tid = test_registration()
    if not ok_reg:
        print(f"\n{_FAIL} Registration failed — aborting.\n")
        return 1

    clarified = test_designer_clarification(tid)
    if not clarified:
        info("Skipping designer completion check")

    built, app_name = test_designer_completion(tid)
    if not built:
        info(f"Designer did not confirm build — skipping pipeline wait")
    else:
        app_active = test_app_build(tid, app_name)
        if app_active:
            test_app_url(tid, app_name)
            test_run_logs(app_name)

    # Summary
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
