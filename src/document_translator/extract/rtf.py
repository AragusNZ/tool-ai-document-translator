"""Extract plain text from RTF files."""
from __future__ import annotations

import re


def strip_rtf(text: str) -> tuple[str, bool]:
    """Return (plain text, used_regex_fallback)."""
    try:
        from striprtf.striprtf import rtf_to_text

        return rtf_to_text(text), False
    except ImportError:
        pass

    text = re.sub(r"\\[a-z]+\d* ?|\\\{|\\\}|\\'[0-9a-fA-F]{2}", "", text)
    text = re.sub(r"[{}]", "", text)
    text = re.sub(r"\r\n", "\n", text)
    return text.strip(), True
