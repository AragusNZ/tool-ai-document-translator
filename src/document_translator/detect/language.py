from __future__ import annotations

from document_translator.config.defaults import DEFAULT_LANG_CONFIDENCE, LANGUAGE_SAMPLE_MAX_CHARS
from document_translator.detect.ai import detect_language_ai
from document_translator.lib.llm.protocol import LLMClient
from document_translator.lib.text.chunker import chunk_document

try:
    from langdetect import DetectorFactory, LangDetectException, detect_langs

    DetectorFactory.seed = 0
    _HAS_LANGDETECT = True
except ImportError:
    _HAS_LANGDETECT = False
    LangDetectException = Exception  # type: ignore[misc, assignment]


def detect_language(
    text: str,
    *,
    llm: LLMClient | None = None,
    confidence_threshold: float = DEFAULT_LANG_CONFIDENCE,
) -> tuple[str, float, bool]:
    """Return (lang_code, confidence, used_ai_fallback)."""
    sample_parts: list[str] = []
    chunks = chunk_document(text, max_chars=LANGUAGE_SAMPLE_MAX_CHARS, overlap_sentences=0)
    if chunks:
        sample_parts.append(chunks[0].text)
        if len(chunks) > 2:
            sample_parts.append(chunks[len(chunks) // 2].text)
        if len(chunks) > 1:
            sample_parts.append(chunks[-1].text)
    sample = "\n\n".join(sample_parts)[:8000]

    if len(sample.strip()) < 40:
        if llm:
            return detect_language_ai(llm, sample), 0.5, True
        return "unknown", 0.0, False

    if not _HAS_LANGDETECT:
        if llm:
            return detect_language_ai(llm, sample), 0.7, True
        return "unknown", 0.0, False

    try:
        langs = detect_langs(sample)
    except LangDetectException:
        if llm:
            return detect_language_ai(llm, sample), 0.5, True
        return "unknown", 0.0, False

    if not langs:
        if llm:
            return detect_language_ai(llm, sample), 0.5, True
        return "unknown", 0.0, False

    top = langs[0]
    if top.prob >= confidence_threshold:
        return top.lang, float(top.prob), False

    if llm:
        ai_lang = detect_language_ai(llm, sample)
        return ai_lang, float(top.prob), True
    return top.lang, float(top.prob), False
