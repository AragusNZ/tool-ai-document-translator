from __future__ import annotations

import re

from rapidfuzz import fuzz

from document_translator.config.defaults import DEFAULT_SIMILARITY_THRESHOLD

PROTECTED_TOKEN_RE = re.compile(
    r"""
    \b\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}\b|
    \b\d+(?:[.,]\d+)?%|
    \$\s?\d+(?:[.,]\d+)?|
    \b\d+(?:[.,]\d+)?\b
    """,
    re.VERBOSE,
)


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


PROPER_NOUN_RE = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b")


def extract_protected_tokens(text: str) -> set[str]:
    tokens = {m.group(0).strip() for m in PROTECTED_TOKEN_RE.finditer(text)}
    tokens.update(m.group(0).strip() for m in PROPER_NOUN_RE.finditer(text))
    return tokens


def protected_tokens_differ(a: str, b: str) -> bool:
    return extract_protected_tokens(a) != extract_protected_tokens(b)


def compare_chunk_pair(
    text_1: str,
    text_2: str,
    *,
    similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
) -> list[dict[str, object]]:
    sentences_1 = split_sentences(text_1)
    sentences_2 = split_sentences(text_2)
    flagged: list[dict[str, object]] = []

    max_len = max(len(sentences_1), len(sentences_2))
    for i in range(max_len):
        s1 = sentences_1[i] if i < len(sentences_1) else ""
        s2 = sentences_2[i] if i < len(sentences_2) else ""
        if not s1 and not s2:
            continue
        score = fuzz.ratio(s1, s2) if s1 and s2 else 0.0
        token_diff = protected_tokens_differ(s1, s2) if s1 and s2 else bool(s1) != bool(s2)
        if score < similarity_threshold or token_diff:
            flagged.append(
                {
                    "sentence_index": i,
                    "translation_1": s1,
                    "translation_2": s2,
                    "similarity": score,
                    "protected_token_mismatch": token_diff,
                }
            )
    return flagged
