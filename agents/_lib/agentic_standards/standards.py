"""
Standards loader — loads YAML standards files and formats them for LLM injection.

This is the canonical replacement for the hand-rolled loader in
orchestrator/standards.py. All agents and the orchestrator should use
this function.

Usage:
    from agentic_standards.standards import load_platform_standards, load_agent_standards

    # In orchestrator or any agent's system prompt setup:
    platform = load_platform_standards()
    agent = load_agent_standards("coder")
    system_prompt = f"You are the coder agent.\n\n{platform}\n\n{agent}"
"""

from __future__ import annotations

import importlib.resources
from pathlib import Path

import yaml


def _standards_dir() -> Path:
    """Return the path to the bundled standards/ directory."""
    # When installed as a package, use importlib.resources
    try:
        ref = importlib.resources.files("agentic_standards") / ".." / "standards"
        return Path(str(ref)).resolve()
    except Exception:
        # Fall back to sibling directory during local development
        return Path(__file__).parent.parent / "standards"


def _load_yaml_files(directory: Path) -> str:
    """Load all *.yaml files in a directory and format as markdown."""
    if not directory.exists():
        return ""

    sections: list[str] = []
    for yaml_file in sorted(directory.glob("*.yaml")):
        with yaml_file.open() as f:
            content = f.read().strip()
        sections.append(f"### {yaml_file.stem}\n```yaml\n{content}\n```")

    return "\n\n".join(sections)


def load_platform_standards() -> str:
    """
    Load and format the platform-level standards (naming, patterns, security).

    Returns a markdown string suitable for injection into any agent's system prompt.
    Returns empty string if the standards directory is not found (safe default).
    """
    standards_dir = _standards_dir()
    return _load_yaml_files(standards_dir)


def load_agent_standards(role: str) -> str:
    """
    Load and format the agent-specific standards for a given role.

    Args:
        role: Agent role name (e.g. 'coder', 'designer', 'tester').

    Returns:
        A markdown string with the agent's behavioral contract.
        Returns empty string if the agent YAML is not found.
    """
    agents_dir = _standards_dir() / "agents"
    yaml_path = agents_dir / f"{role}.yaml"

    if not yaml_path.exists():
        return ""

    with yaml_path.open() as f:
        content = f.read().strip()

    return f"### Agent contract: {role}\n```yaml\n{content}\n```"


def load_all_standards(role: str) -> str:
    """
    Load platform standards + agent-specific standards for a given role.

    This is the primary entry point for agent system prompt construction.

    Args:
        role: Agent role name.

    Returns:
        Combined markdown string with all relevant standards.
    """
    platform = load_platform_standards()
    agent = load_agent_standards(role)

    parts = [p for p in [platform, agent] if p]
    return "\n\n---\n\n".join(parts)
