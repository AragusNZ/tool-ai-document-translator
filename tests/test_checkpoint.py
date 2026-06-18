from __future__ import annotations

from pathlib import Path

from document_translator.storage.checkpoint import (
    CheckpointStage,
    CheckpointState,
    load_checkpoint,
    load_completed_chunks,
    read_layout_body_checkpoint,
    source_text_hash,
    write_checkpoint,
    write_chunk_checkpoint,
    write_layout_body_checkpoint,
)


def test_source_text_hash_is_stable() -> None:
    text = "Hello world."
    assert source_text_hash(text) == source_text_hash(text)
    assert source_text_hash("  Hello world.  ") == source_text_hash("  Hello world.  ")


def test_write_and_load_checkpoint(tmp_path: Path) -> None:
    path = tmp_path / "checkpoint.json"
    state = CheckpointState(
        stage=CheckpointStage.TRANSLATING_PASS1,
        chunk_index=2,
        pass_num=1,
        source_hash="abc123",
        llm="cursor:composer-2.5",
        translation_mode="quick",
        chunk_count=5,
        target_lang="en",
    )
    write_checkpoint(path, state)
    loaded = load_checkpoint(path)
    assert loaded is not None
    assert loaded.stage == CheckpointStage.TRANSLATING_PASS1
    assert loaded.chunk_index == 2


def test_load_completed_chunks_stops_on_gap(tmp_path: Path) -> None:
    checkpoints_dir = tmp_path / "checkpoints"
    write_chunk_checkpoint(
        checkpoints_dir,
        pass_num=1,
        chunk_index=0,
        text="chunk zero",
        source_hash="hash",
        llm="cursor:composer-2.5",
    )
    write_chunk_checkpoint(
        checkpoints_dir,
        pass_num=1,
        chunk_index=1,
        text="chunk one",
        source_hash="hash",
        llm="cursor:composer-2.5",
    )
    completed = load_completed_chunks(
        checkpoints_dir,
        pass_num=1,
        chunk_count=3,
        source_hash="hash",
        llm="cursor:composer-2.5",
    )
    assert completed == {0: "chunk zero", 1: "chunk one"}


def test_layout_body_checkpoint_round_trip(tmp_path: Path) -> None:
    extract_dir = tmp_path / "checkpoints" / "extract"
    write_layout_body_checkpoint(extract_dir, "layout source\n")
    assert read_layout_body_checkpoint(extract_dir) == "layout source\n"
    assert read_layout_body_checkpoint(tmp_path / "missing") is None
