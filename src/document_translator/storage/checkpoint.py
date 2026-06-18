from __future__ import annotations

import hashlib
import json
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field

from document_translator.extract.common import normalize_text


class CheckpointStage(str, Enum):
    EXTRACTED = "extracted"
    TRANSLATING_PASS1 = "translating_pass1"
    TRANSLATING_PASS2 = "translating_pass2"
    RECONCILING = "reconciling"
    COMPLETED = "completed"


class CheckpointState(BaseModel):
    version: int = 1
    stage: CheckpointStage
    chunk_index: int = -1
    pass_num: int = 1
    source_hash: str
    llm: str
    translation_mode: str
    chunk_count: int = 0
    target_lang: str = "en"


def source_text_hash(text: str) -> str:
    normalized = normalize_text(text).strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def load_checkpoint(path: Path) -> CheckpointState | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return CheckpointState.model_validate(payload)
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def write_checkpoint(path: Path, state: CheckpointState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(state.model_dump_json(indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def chunk_checkpoint_name(*, pass_num: int, chunk_index: int) -> str:
    return f"translate-pass{pass_num}-chunk-{chunk_index:04d}.md"


def chunk_checkpoint_meta_name(*, pass_num: int, chunk_index: int) -> str:
    return f"translate-pass{pass_num}-chunk-{chunk_index:04d}.meta.json"


def load_completed_chunks(
    checkpoints_dir: Path,
    *,
    pass_num: int,
    chunk_count: int,
    source_hash: str,
    llm: str,
) -> dict[int, str]:
    completed: dict[int, str] = {}
    for index in range(chunk_count):
        path = checkpoints_dir / chunk_checkpoint_name(pass_num=pass_num, chunk_index=index)
        meta_path = checkpoints_dir / chunk_checkpoint_meta_name(pass_num=pass_num, chunk_index=index)
        if not path.is_file() or not meta_path.is_file():
            break
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            break
        if meta.get("source_hash") != source_hash or meta.get("llm") != llm:
            break
        completed[index] = path.read_text(encoding="utf-8")
    return completed


def write_chunk_checkpoint(
    checkpoints_dir: Path,
    *,
    pass_num: int,
    chunk_index: int,
    text: str,
    source_hash: str,
    llm: str,
) -> None:
    checkpoints_dir.mkdir(parents=True, exist_ok=True)
    chunk_path = checkpoints_dir / chunk_checkpoint_name(pass_num=pass_num, chunk_index=chunk_index)
    meta_path = checkpoints_dir / chunk_checkpoint_meta_name(pass_num=pass_num, chunk_index=chunk_index)
    chunk_path.write_text(text, encoding="utf-8")
    meta_path.write_text(
        json.dumps(
            {
                "source_hash": source_hash,
                "llm": llm,
                "pass_num": pass_num,
                "chunk_index": chunk_index,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def write_extract_chunk_checkpoints(
    extract_dir: Path,
    *,
    chunks: list[str],
) -> None:
    extract_dir.mkdir(parents=True, exist_ok=True)
    for index, text in enumerate(chunks):
        path = extract_dir / f"chunk-{index:04d}.md"
        path.write_text(text, encoding="utf-8")


LAYOUT_BODY_CHECKPOINT = "layout-body.md"


def layout_body_checkpoint_path(extract_dir: Path) -> Path:
    return extract_dir / LAYOUT_BODY_CHECKPOINT


def write_layout_body_checkpoint(extract_dir: Path, text: str) -> None:
    extract_dir.mkdir(parents=True, exist_ok=True)
    layout_body_checkpoint_path(extract_dir).write_text(text, encoding="utf-8")


def read_layout_body_checkpoint(extract_dir: Path) -> str | None:
    path = layout_body_checkpoint_path(extract_dir)
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")
