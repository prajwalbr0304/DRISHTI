"""Container-safe repo-relative data path resolution.

The deployed AppSail image (services/ml/Dockerfile.appsail) copies ONLY ``app/``
and ``sql/`` into ``/app`` — the wider repo tree (``infra/``, ``datagen/``,
``models/``) is intentionally absent. Modules that load repo data files
(serving-export JSONL, datagen fixtures) must therefore NOT assume a fixed
``Path(__file__).resolve().parents[N]`` repo-root depth: in the image that index
does not exist and raises ``IndexError`` at import, which previously crashed
AppSail startup (Prompt 22 §A.4).

:func:`repo_data_path` walks this file's ancestors and returns the first existing
match, or ``None`` when the repo tree is absent (the minimal image). Callers then
degrade gracefully: the deployed operational data comes from Catalyst Data Store
(seeded via ``infra/catalyst/ds-import``), not these local files.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional


def repo_data_path(*relative_parts: str) -> Optional[Path]:
    """Return ``<repo_root>/<relative_parts...>`` if it exists in the current
    checkout, else ``None`` (e.g. inside the minimal AppSail image).

    The repo root is found by walking this file's ancestors and returning the
    first ancestor for which the relative path exists — so it is independent of
    how deep ``app/`` sits (repo checkout vs ``/app`` in the container). Never
    raises for a missing path.
    """
    rel = Path(*relative_parts)
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / rel
        if candidate.exists():
            return candidate
    return None
