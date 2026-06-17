from document_translator.lib.text.chunker import chunk_document, reassemble_chunks


def test_chunk_document_splits_long_text() -> None:
    text = "Intro\n\n" + ("Word " * 800)
    chunks = chunk_document(text, max_chars=500, overlap_sentences=1)
    assert len(chunks) >= 2
    assert all(c.text for c in chunks)


def test_chunk_preserves_headings() -> None:
    text = "# Title\n\nParagraph one.\n\n## Section\n\nParagraph two."
    chunks = chunk_document(text, max_chars=2000, overlap_sentences=0)
    assert any("Title" in c.heading_context or "# Title" in c.text for c in chunks)


def test_reassemble_chunks() -> None:
    out = reassemble_chunks(["First chunk.", "Second chunk."])
    assert "First chunk." in out
    assert "Second chunk." in out
