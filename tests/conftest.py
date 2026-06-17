from __future__ import annotations

import zipfile
from collections.abc import Callable
from pathlib import Path

import pytest

from document_translator.config.formats import ExportFormat
from document_translator.config.settings import PipelineConfig
from document_translator.lib.llm import MockLLMClient


@pytest.fixture
def mock_llm() -> MockLLMClient:
    return MockLLMClient(prefix="[EN] ")


@pytest.fixture
def spanish_contract(tmp_path: Path) -> Path:
    text = """ACUERDO DE COMPRAVENTA

POR CUANTO las partes convienen mutuamente en celebrar el presente contrato.
El Vendedor entregará la mercancía dentro de los treinta días siguientes.
El Comprador podrá rescindir el contrato mediante notificación escrita con diez días de anticipación.
La indemnización cubrirá toda responsabilidad derivada del incumplimiento del presente acuerdo contractual.
Las partes acuerdan someterse a la jurisdicción de los tribunales competentes de esta ciudad.
"""
    path = tmp_path / "contract.txt"
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def english_doc(tmp_path: Path) -> Path:
    text = """WHEREAS the parties hereby agree to this contract.
The Seller shall deliver the goods within thirty days following the date hereof.
The Buyer may terminate this agreement upon written notice to the other party.
The parties agree to submit to the jurisdiction of the competent courts.
"""
    path = tmp_path / "english_contract.txt"
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def pipeline_config(tmp_path: Path) -> PipelineConfig:
    return PipelineConfig(runs_dir=tmp_path / "runs", root=tmp_path)


@pytest.fixture
def touch_export() -> Callable[[Path, Path, ExportFormat], None]:
    def _touch_export(source: Path, target: Path, fmt: ExportFormat) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("exported", encoding="utf-8")

    return _touch_export


@pytest.fixture
def minimal_pdf(tmp_path: Path) -> Path:
    import fitz

    path = tmp_path / "sample.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Sample PDF text for extraction testing.")
    doc.save(path)
    doc.close()
    return path


@pytest.fixture
def scanned_pdf(tmp_path: Path) -> Path:
    import fitz

    path = tmp_path / "scanned.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.save(path)
    doc.close()
    return path


@pytest.fixture
def minimal_docx(tmp_path: Path) -> Path:
    path = tmp_path / "sample.docx"
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""
    document = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body><w:p><w:r><w:t>Hello DOCX world</w:t></w:r></w:p></w:body>
</w:document>"""
    rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("word/document.xml", document)
    return path
