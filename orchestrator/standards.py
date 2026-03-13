"""Load architecture standards from the standards/ directory and format them
for injection into the LLM system prompt."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

STANDARDS_DIR = Path(os.getenv("STANDARDS_DIR", "/app/standards"))


def _load_yaml(path: Path) -> dict:
    with path.open() as f:
        return yaml.safe_load(f) or {}


def load_standards() -> str:
    """Return a formatted string of all standards for use in a system prompt.

    Returns an empty string if the standards directory does not exist or
    contains no YAML files — this keeps Phase 1 behaviour intact during tests.
    """
    if not STANDARDS_DIR.is_dir():
        return ""

    files = sorted(STANDARDS_DIR.glob("*.yaml"))
    if not files:
        return ""

    sections: list[str] = []
    for path in files:
        name = path.stem.replace("_", " ").title()
        data = _load_yaml(path)
        sections.append(f"### {name}\n```yaml\n{yaml.dump(data, default_flow_style=False, sort_keys=False).strip()}\n```")

    return "\n\n".join(sections)
