from __future__ import annotations

DEFAULT_TARGET_LANG = "en"
DEFAULT_LLM_SELECTOR = "cursor:composer-2.5"
DEFAULT_TRANSLATION_MODEL = "composer-2.5"
DEFAULT_CHUNK_SIZE = 2500
DEFAULT_CHUNK_OVERLAP = 2
DEFAULT_SIMILARITY_THRESHOLD = 92.0
DEFAULT_LANG_CONFIDENCE = 0.85
DEFAULT_MAX_CONCURRENT_CHUNKS = 4
LANGUAGE_SAMPLE_MAX_CHARS = 2000
DOCUMENT_SUMMARY_MAX_CHARS = 500
TRANSLATION_CONTEXT_MAX_CHARS = 2000
LOW_TEXT_DENSITY_CHARS_PER_PAGE = 50
PDF_OCR_MIN_CHARS_PER_PAGE = 20
DEFAULT_PDF_OCR_LANGUAGES = "eng"
LARGE_INPUT_BYTES = 20_000_000
REPLACEMENT_CHAR = "\ufffd"

DEFAULT_MAX_RETRIES = 5
DEFAULT_RETRY_BASE_DELAY = 1.0
DEFAULT_RETRY_MAX_DELAY = 120.0

LEGAL_KEYWORDS: tuple[str, ...] = (
    r"\bwhereas\b",
    r"\bhereby\b",
    r"\bherein\b",
    r"\bthereof\b",
    r"\bindemnif",
    r"\bparty\b",
    r"\bparties\b",
    r"\bagreement\b",
    r"\bcontract\b",
    r"\bshall\b",
    r"\bliability\b",
    r"\bjurisdiction\b",
    r"\bgoverning law\b",
    r"\bwitnesseth\b",
)
