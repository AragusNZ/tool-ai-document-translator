# Golden extract fixtures

Programmatic PDFs generated in-repo for extraction regression tests. **MIT-licensed** (same as document-translator); no third-party document content.

## Regenerate

```bash
python tests/fixtures/extract/build_fixtures.py
```

This writes PDFs and refreshes `golden_manifest.json` (PyMuPDF cases always; LiteParse cases when `[extract-liteparse]` is installed).

## Update hashes after intentional extract changes

```bash
UPDATE_GOLDEN=1 pytest tests/test_extract_regression.py
```

Commit updated `golden_manifest.json` with the code change.

## Layout

| File | Purpose |
|------|---------|
| `single_page_text.pdf` | Basic text layer |
| `multi_page_three.pdf` | Multi-page join |
| `slide_markers.pdf` | `-- N of M --` normalization |
| `unicode_symbols.pdf` | UTF-8 content |
| `empty_page_between.pdf` | Blank page handling |
| `dual_column_text.pdf` | Two text regions on one page |
| `whitespace_edges.pdf` | Padding / normalization |
| `legal_keywords.pdf` | Longer prose sample |
| `golden_manifest.json` | Expected normalized text SHA-256 per backend |

Golden tests run with `pdf_ocr=false` for deterministic hashes across CI hosts.
