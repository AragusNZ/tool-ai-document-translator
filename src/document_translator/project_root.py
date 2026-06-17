from __future__ import annotations

import os
from pathlib import Path


def get_project_root() -> Path:
    override = os.environ.get("DOCUMENT_TRANSLATOR_ROOT")
    if override:
        return Path(override).resolve()
    return Path(__file__).resolve().parents[2]
