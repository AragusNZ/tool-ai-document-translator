# Third-party notices

document-translator is licensed under the [MIT License](LICENSE).

When you install or redistribute this software, the following third-party components may be included depending on your install profile.

## Default install (`pip install document-translator`)

| Component | Role | License |
|-----------|------|---------|
| [PyMuPDF](https://pymupdf.readthedocs.io/) | Default PDF text extraction | [AGPL-3.0](https://www.gnu.org/licenses/agpl-3.0.html) |
| [WeasyPrint](https://weasyprint.org/) | PDF export | [BSD-3-Clause](https://github.com/Kozea/WeasyPrint/blob/main/LICENSE) |
| [Mammoth](https://github.com/mwilliamson/python-mammoth) | DOCX extraction | [BSD-2-Clause](https://github.com/mwilliamson/python-mammoth/blob/master/LICENSE) |
| Other Python dependencies | See `pyproject.toml` | Per-package (mostly permissive) |

System packages in the published Docker image (not Python wheels) include Pandoc, Tesseract, LibreOffice, and WeasyPrint system libraries — see the [Dockerfile](Dockerfile) `apt-get` list.

## Optional: LiteParse extraction backend

Install with:

```bash
pip install 'document-translator[extract-liteparse]'
```

Or build the Docker image with `WITH_LITEPARSE=1` (see [docs/integration/Docker.md](docs/integration/Docker.md)).

| Component | Role | License |
|-----------|------|---------|
| [LiteParse](https://github.com/run-llama/liteparse) | Optional extract backend (`--extract-backend liteparse`) | [Apache-2.0](https://www.apache.org/licenses/LICENSE-2.0) |
| [PDFium](https://pdfium.googlesource.com/pdfium/) | Bundled inside LiteParse wheels for PDF rendering/text | See LiteParse wheel / upstream PDFium license |

LiteParse is maintained by LlamaIndex (run-llama). document-translator does not modify LiteParse; it calls the published `liteparse` package via a thin adapter in `src/document_translator/extract/backends/liteparse.py`.

### Apache-2.0 redistribution (LiteParse)

If you redistribute document-translator in a form that includes LiteParse (for example a Docker image built with `WITH_LITEPARSE=1`), you must:

1. Retain LiteParse and PDFium license/attribution notices as provided in the installed `liteparse` distribution.
2. Include a copy of the Apache License 2.0 (or a pointer to https://www.apache.org/licenses/LICENSE-2.0) with your distribution.
3. State any modifications you make to LiteParse source (none are made in the default document-translator integration).

## Sample documents and benchmarks

Do not commit third-party PDFs, slide decks, or images into this repository without verifying their license. The `tools/extract-eval/` harness and future golden extraction fixtures must use documents you have rights to use (your own files, explicit open licenses, or anonymized corpora). LiteParse demo files under a local `other-projects/liteparse/` checkout are for developer reference only and are not redistributed with document-translator.
