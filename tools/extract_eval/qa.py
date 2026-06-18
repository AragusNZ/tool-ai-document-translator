from __future__ import annotations

from dataclasses import dataclass, field

from tools.extract_eval.providers.base import BenchmarkRow


@dataclass(frozen=True)
class QACheck:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class QAResult:
    file: str
    backend: str
    checks: list[QACheck] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    @property
    def failures(self) -> list[str]:
        return [f"{check.name}: {check.detail}" for check in self.checks if not check.passed]


def score_benchmark_row(
    row: BenchmarkRow,
    *,
    min_chars: int = 1,
    expected_hash: str | None = None,
    actual_hash: str | None = None,
) -> QAResult:
    checks: list[QACheck] = []
    if row.error:
        checks.append(QACheck("extract_ok", False, row.error))
    else:
        checks.append(QACheck("extract_ok", True))
        char_count = row.chars or 0
        checks.append(
            QACheck(
                "min_chars",
                char_count >= min_chars,
                f"{char_count} chars (min {min_chars})",
            )
        )
        if row.pages is not None:
            checks.append(
                QACheck(
                    "has_pages",
                    row.pages > 0,
                    f"{row.pages} pages",
                )
            )
    if expected_hash is not None and actual_hash is not None:
        checks.append(
            QACheck(
                "golden_hash",
                actual_hash == expected_hash,
                f"expected {expected_hash[:12]}… got {actual_hash[:12]}…",
            )
        )
    return QAResult(file=row.file, backend=row.backend, checks=checks)


def summarize_qa(results: list[QAResult]) -> dict[str, float | int]:
    total = len(results)
    passed = sum(1 for result in results if result.passed)
    return {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": round((passed / total) * 100, 1) if total else 100.0,
    }
