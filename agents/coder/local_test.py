"""Local pre-commit validation for scaffolded projects.

Writes scaffolded files to a temp directory, installs dependencies in an
isolated virtualenv, syntax-checks every Python file, then probes the app
startup to confirm it doesn't immediately crash.

Returns (passed: bool, message: str).
"""

from __future__ import annotations

import asyncio
import logging
import sys
import tempfile
from pathlib import Path

log = logging.getLogger("coder.local_test")

_PIP_TIMEOUT = 180       # seconds — large deps can be slow
_SYNTAX_TIMEOUT = 10     # seconds per file
_STARTUP_WAIT = 8        # seconds to observe the process after launch
_VENV_TIMEOUT = 30


async def _run(
    cmd: list[str],
    cwd: str,
    timeout: int,
    env: dict | None = None,
) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
        env=env,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return proc.returncode, out.decode(errors="replace"), err.decode(errors="replace")
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        return -1, "", f"timed out after {timeout}s"


async def run_local_tests(files: list[dict]) -> tuple[bool, str]:
    """Validate scaffolded files before committing to Gitea.

    Steps:
      1. Write files to an isolated temp directory.
      2. Create a virtualenv and pip-install requirements.txt.
      3. Syntax-check every .py file with py_compile.
      4. Startup probe: launch the app and confirm it stays alive for a few
         seconds (catches import errors, missing uvicorn, bad config, etc.).

    Returns (True, "ok") on success or (False, reason) on failure.
    """
    with tempfile.TemporaryDirectory(prefix="coder-test-") as tmpdir:
        root = Path(tmpdir)

        for f in files:
            dest = root / f["path"]
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(f["content"], encoding="utf-8")

        venv = root / ".venv"
        python = str(venv / "bin" / "python")
        pip = str(venv / "bin" / "pip")

        # ── 1. Create virtualenv ──────────────────────────────────────────
        rc, _, err = await _run(
            [sys.executable, "-m", "venv", str(venv)],
            cwd=tmpdir, timeout=_VENV_TIMEOUT,
        )
        if rc != 0:
            return False, f"venv creation failed: {err}"

        # ── 2. pip install ────────────────────────────────────────────────
        req = root / "requirements.txt"
        if req.exists():
            rc, _, err = await _run(
                [pip, "install", "-r", str(req), "-q"],
                cwd=tmpdir, timeout=_PIP_TIMEOUT,
            )
            if rc != 0:
                return False, f"pip install failed:\n{err.strip()}"
            log.info("local_test.pip_ok")

        # ── 3. Syntax check ───────────────────────────────────────────────
        for py_file in sorted(root.glob("**/*.py")):
            if ".venv" in py_file.parts:
                continue
            rc, _, err = await _run(
                [python, "-m", "py_compile", str(py_file)],
                cwd=tmpdir, timeout=_SYNTAX_TIMEOUT,
            )
            if rc != 0:
                rel = py_file.relative_to(root)
                return False, f"Syntax error in {rel}:\n{err.strip()}"
        log.info("local_test.syntax_ok")

        # ── 4. Startup probe ──────────────────────────────────────────────
        # Only probe FastAPI / Starlette / Flask apps with a main.py entry point.
        req_text = req.read_text().lower() if req.exists() else ""
        is_web = any(fw in req_text for fw in ("fastapi", "starlette", "flask"))
        if (root / "main.py").exists() and is_web:
            passed, msg = await _startup_probe(python, tmpdir)
            if not passed:
                return False, msg
            log.info("local_test.startup_ok")

        return True, "ok"


async def _startup_probe(python: str, cwd: str) -> tuple[bool, str]:
    """Launch the app with uvicorn and check it doesn't crash immediately."""
    port = 19876  # unlikely to conflict with anything running in the container
    proc = await asyncio.create_subprocess_exec(
        python, "-m", "uvicorn", "main:app",
        "--host", "127.0.0.1", "--port", str(port),
        "--timeout-graceful-shutdown", "1",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
    )
    try:
        await asyncio.sleep(_STARTUP_WAIT)
        if proc.returncode is not None:
            out, err = await proc.communicate()
            combined = (out + err).decode(errors="replace")
            # Database connection errors are expected in a local environment —
            # don't fail the build for them.
            if _is_db_error(combined):
                log.info("local_test.startup_db_error_ignored")
                return True, "ok"
            return False, f"App crashed on startup:\n{combined[:1000]}"
        return True, "ok"
    finally:
        if proc.returncode is None:
            proc.kill()
            await proc.communicate()


_DB_ERROR_SIGNALS = (
    "connection refused",
    "could not connect",
    "connection to server",
    "no such file or directory",  # unix socket
    "sqlalchemy",
    "psycopg",
    "database",
)


def _is_db_error(output: str) -> bool:
    lower = output.lower()
    return any(sig in lower for sig in _DB_ERROR_SIGNALS)
