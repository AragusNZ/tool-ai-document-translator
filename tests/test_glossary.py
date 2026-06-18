from __future__ import annotations

import json
from pathlib import Path

import pytest

from document_translator.translate.glossary import Glossary, load_glossary_file, parse_glossary_payload, resolve_glossary
from document_translator.translate.service import _build_user_prompt, build_translation_system
from document_translator.lib.text.chunker import TextChunk


def test_parse_glossary_payload_string_entries() -> None:
    glossary = parse_glossary_payload(
        {
            "Acme Corp": "Acme Corp",
            "Vendedor": "Seller",
        }
    )
    assert "Acme Corp" in glossary.do_not_translate
    assert glossary.preferred["Vendedor"] == "Seller"


def test_parse_glossary_payload_object_entry() -> None:
    glossary = parse_glossary_payload(
        {
            "Beta LLC": {"do_not_translate": True},
            "shall": {"preferred": "shall"},
        }
    )
    assert "Beta LLC" in glossary.do_not_translate
    assert "shall" in glossary.do_not_translate


def test_glossary_in_prompt() -> None:
    glossary = Glossary(preferred={"Vendedor": "Seller"}, do_not_translate={"Acme Corp"})
    system = build_translation_system("en", glossary=glossary)
    assert "glossary" in system.casefold()

    chunk = TextChunk(index=0, text="El Vendedor firmó.", heading_context="")
    user = _build_user_prompt(
        chunk,
        "es",
        "en",
        is_legal=True,
        glossary=glossary,
    )
    assert "Glossary terms:" in user
    assert "Vendedor" in user
    assert "Acme Corp" in user


def test_load_glossary_file(tmp_path: Path) -> None:
    path = tmp_path / "glossary.json"
    path.write_text(json.dumps({"Seller": "Seller", "Comprador": "Buyer"}), encoding="utf-8")
    glossary = load_glossary_file(path)
    assert glossary.preferred["Comprador"] == "Buyer"
    assert "Seller" in glossary.do_not_translate


def test_resolve_glossary_merges_inline_and_file(tmp_path: Path) -> None:
    path = tmp_path / "glossary.json"
    path.write_text(json.dumps({"Acme": "Acme"}), encoding="utf-8")
    glossary = resolve_glossary(glossary_path=path, inline_glossary={"Buyer": "Buyer"})
    assert "Acme" in glossary.do_not_translate
    assert "Buyer" in glossary.do_not_translate


def test_protected_tokens_include_glossary() -> None:
    from document_translator.reconcile.compare import protected_tokens_differ

    glossary = Glossary(preferred={"Vendedor": "Seller"}, do_not_translate=set())
    tokens = glossary.protected_tokens()
    assert "Seller" in tokens
    assert not protected_tokens_differ("The Seller agreed.", "The Seller agreed.", extra_tokens=tokens)
    assert protected_tokens_differ("The Seller agreed.", "The Vendor agreed.", extra_tokens=tokens)
