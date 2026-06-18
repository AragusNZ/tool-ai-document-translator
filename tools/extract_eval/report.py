from __future__ import annotations

import html
from datetime import UTC, datetime
from pathlib import Path

from tools.extract_eval.qa import QAResult, summarize_qa
from tools.extract_eval.providers.base import BenchmarkRow


def render_html_report(
    *,
    rows: list[BenchmarkRow],
    qa_results: list[QAResult],
    title: str = "Extract evaluation report",
) -> str:
    summary = summarize_qa(qa_results)
    generated = datetime.now(UTC).isoformat()
    qa_by_key = {(result.file, result.backend): result for result in qa_results}

    table_rows: list[str] = []
    for row in rows:
        qa = qa_by_key.get((row.file, row.backend))
        status = "pass" if qa and qa.passed else "fail"
        if row.error:
            detail = html.escape(row.error)
        else:
            detail = (
                f"{row.chars} chars, {row.pages} pages, {row.elapsed_ms} ms, "
                f"{html.escape(str(row.conversion_method or ''))}"
            )
        failures = ""
        if qa and qa.failures:
            failures = "<ul>" + "".join(f"<li>{html.escape(item)}</li>" for item in qa.failures) + "</ul>"
        table_rows.append(
            "<tr>"
            f"<td>{html.escape(row.file)}</td>"
            f"<td>{html.escape(row.backend)}</td>"
            f'<td class="{status}">{status}</td>'
            f"<td>{detail}</td>"
            f"<td>{failures}</td>"
            "</tr>"
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{html.escape(title)}</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 2rem; color: #111; }}
    h1 {{ margin-bottom: 0.2rem; }}
    .meta {{ color: #555; margin-bottom: 1.5rem; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #ddd; padding: 0.5rem 0.75rem; vertical-align: top; }}
    th {{ background: #f5f5f5; text-align: left; }}
    .pass {{ color: #0a7a2f; font-weight: 600; }}
    .fail {{ color: #b00020; font-weight: 600; }}
    .summary {{ margin: 1rem 0 1.5rem; }}
  </style>
</head>
<body>
  <h1>{html.escape(title)}</h1>
  <p class="meta">Generated {html.escape(generated)}</p>
  <p class="summary">
    QA pass rate: <strong>{summary['pass_rate']}%</strong>
    ({summary['passed']}/{summary['total']} cases passed)
  </p>
  <table>
    <thead>
      <tr>
        <th>File</th>
        <th>Backend</th>
        <th>QA</th>
        <th>Extract</th>
        <th>Failures</th>
      </tr>
    </thead>
    <tbody>
      {''.join(table_rows)}
    </tbody>
  </table>
</body>
</html>
"""


def write_html_report(path: Path, html_content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html_content, encoding="utf-8")
