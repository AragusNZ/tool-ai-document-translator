from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from document_translator.errors import IssueCode, PipelineError
from document_translator.types import PipelineStage


@dataclass
class Glossary:
    """Source-term glossary with preferred translations and do-not-translate terms."""

    preferred: dict[str, str] = field(default_factory=dict)
    do_not_translate: set[str] = field(default_factory=set)

    def __len__(self) -> int:
        return len(self.preferred) + len(self.do_not_translate)

    def protected_tokens(self) -> set[str]:
        tokens = set(self.do_not_translate)
        tokens.update(self.preferred.values())
        return {token.strip() for token in tokens if token.strip()}

    def format_for_prompt(self) -> str:
        if not self.preferred and not self.do_not_translate:
            return ""
        lines: list[str] = []
        for term in sorted(self.do_not_translate):
            lines.append(f"- {term!r}: keep unchanged (do not translate)")
        for source, target in sorted(self.preferred.items()):
            if source in self.do_not_translate:
                continue
            lines.append(f"- {source!r} → {target!r}")
        if not lines:
            return ""
        return "Glossary terms:\n" + "\n".join(lines)


def _parse_glossary_entry(source: str, value: Any) -> tuple[str | None, str | None, bool]:
    source = source.strip()
    if not source:
        return None, None, False
    if isinstance(value, dict):
        if value.get("do_not_translate"):
            return source, None, True
        preferred = value.get("preferred")
        if preferred is not None:
            preferred_str = str(preferred).strip()
            if preferred_str and preferred_str.casefold() == source.casefold():
                return source, None, True
            return source, preferred_str or None, False
        return source, None, True
    preferred = str(value).strip()
    if not preferred or preferred.casefold() == source.casefold():
        return source, None, True
    return source, preferred, False


def parse_glossary_payload(payload: object) -> Glossary:
    if not isinstance(payload, dict):
        raise ValueError("glossary must be a JSON object mapping terms to translations")
    preferred: dict[str, str] = {}
    do_not_translate: set[str] = set()
    for raw_source, raw_value in payload.items():
        source, target, dnt = _parse_glossary_entry(str(raw_source), raw_value)
        if source is None:
            continue
        if dnt:
            do_not_translate.add(source)
            continue
        if target:
            preferred[source] = target
    return Glossary(preferred=preferred, do_not_translate=do_not_translate)


def load_glossary_file(path: Path) -> Glossary:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise PipelineError(
            f"Failed to read glossary file: {path}",
            code=IssueCode.CONFIGURATION_ERROR,
            stage=PipelineStage.TRANSLATING,
            cause=exc,
        ) from exc
    except json.JSONDecodeError as exc:
        raise PipelineError(
            f"Invalid glossary JSON: {path}",
            code=IssueCode.CONFIGURATION_ERROR,
            stage=PipelineStage.TRANSLATING,
            cause=exc,
        ) from exc
    try:
        return parse_glossary_payload(payload)
    except ValueError as exc:
        raise PipelineError(
            str(exc),
            code=IssueCode.CONFIGURATION_ERROR,
            stage=PipelineStage.TRANSLATING,
            cause=exc,
        ) from exc


def resolve_glossary(
    *,
    glossary_path: Path | None = None,
    inline_glossary: object | None = None,
) -> Glossary | None:
    glossary: Glossary | None = None
    if glossary_path is not None:
        glossary = load_glossary_file(glossary_path)
    if inline_glossary is not None:
        inline = parse_glossary_payload(inline_glossary)
        if glossary is None:
            glossary = inline
        else:
            glossary = Glossary(
                preferred={**glossary.preferred, **inline.preferred},
                do_not_translate=glossary.do_not_translate | inline.do_not_translate,
            )
    return glossary
