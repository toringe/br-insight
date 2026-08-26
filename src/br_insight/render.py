"""Jinja2 rendering environment for the static-site build.

Task 7 scope: environment setup + ``render_template`` helper. The full
``build()`` pipeline (page fan-out, asset depth handling) lands in Task 8
and builds on this module.
"""

from __future__ import annotations

import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_DIR = REPO_ROOT / "templates"


def get_env() -> Environment:
    """Shared Jinja2 environment loading ``templates/`` from the repo root."""
    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(("html", "xml")),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.globals["now"] = datetime.datetime.now()
    return env


_env: Environment | None = None


def _shared_env() -> Environment:
    global _env
    if _env is None:
        _env = get_env()
    return _env


def render_template(name: str, **ctx):
    """Render ``templates/<name>`` with the given context."""
    template = _shared_env().get_template(name)
    return template.render(**ctx)
