from __future__ import annotations

import re
from dataclasses import dataclass

from document_translator.config.defaults import DEFAULT_CHUNK_OVERLAP, DEFAULT_CHUNK_SIZE


@dataclass
class TextChunk:
    index: int
    text: str
    heading_context: str = ""


_HEADING_RE = re.compile(r"^(#{1,6}\s+.+)$", re.MULTILINE)


def split_into_paragraphs(text: str) -> list[str]:
    blocks: list[str] = []
    current: list[str] = []
    for line in text.splitlines():
        if not line.strip():
            if current:
                blocks.append("\n".join(current))
                current = []
            continue
        if _HEADING_RE.match(line) and current:
            blocks.append("\n".join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        blocks.append("\n".join(current))
    return blocks


def chunk_document(
    text: str,
    *,
    max_chars: int = DEFAULT_CHUNK_SIZE,
    overlap_sentences: int = DEFAULT_CHUNK_OVERLAP,
) -> list[TextChunk]:
    paragraphs = split_into_paragraphs(text)
    chunks: list[TextChunk] = []
    current_heading = ""
    buffer: list[str] = []
    buffer_len = 0

    def sentence_overlap(paragraph: str) -> str:
        sentences = re.split(r"(?<=[.!?])\s+", paragraph.strip())
        if len(sentences) <= overlap_sentences:
            return paragraph
        return " ".join(sentences[-overlap_sentences:])

    def flush() -> None:
        nonlocal buffer, buffer_len
        if not buffer:
            return
        body = "\n\n".join(buffer).strip()
        chunks.append(TextChunk(index=len(chunks), text=body, heading_context=current_heading))
        if overlap_sentences > 0 and buffer:
            overlap = sentence_overlap(buffer[-1])
            buffer = [overlap] if overlap else []
            buffer_len = len(overlap)
        else:
            buffer = []
            buffer_len = 0

    for para in paragraphs:
        if _HEADING_RE.match(para):
            flush()
            current_heading = para.strip()
            buffer = [para]
            buffer_len = len(para)
            continue

        para_len = len(para) + (2 if buffer else 0)
        if buffer_len + para_len > max_chars and buffer:
            flush()
        buffer.append(para)
        buffer_len += para_len

    flush()
    if not chunks and text.strip():
        chunks.append(TextChunk(index=0, text=text.strip(), heading_context=""))
    return chunks


def reassemble_chunks(chunks: list[str]) -> str:
    return "\n\n".join(c.strip() for c in chunks if c.strip()).strip() + "\n"
