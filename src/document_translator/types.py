from __future__ import annotations

from enum import Enum


class JobStatus(str, Enum):
    QUEUED = "queued"
    EXTRACTING = "extracting"
    DETECTING_LANGUAGE = "detecting_language"
    TRANSLATING = "translating"
    RECONCILING = "reconciling"
    EXPORTING = "exporting"
    COMPLETED = "completed"
    COMPLETED_WITH_WARNINGS = "completed_with_warnings"
    FAILED = "failed"


class TranslationMode(str, Enum):
    QUICK = "quick"
    THOROUGH = "thorough"


class PipelineStage(str, Enum):
    EXTRACTING = "extracting"
    DETECTING_LANGUAGE = "detecting_language"
    TRANSLATING = "translating"
    RECONCILING = "reconciling"
    EXPORTING = "exporting"
    COMPLETED = "completed"
    FAILED = "failed"
