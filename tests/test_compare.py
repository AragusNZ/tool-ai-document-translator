from document_translator.reconcile.compare import (
    compare_chunk_pair,
    extract_protected_tokens,
    protected_tokens_differ,
    split_sentences,
)


def test_split_sentences() -> None:
    sents = split_sentences("Hello world. How are you? Fine!")
    assert len(sents) == 3


def test_compare_flags_divergent_sentences() -> None:
    a = "The party shall pay within 30 days."
    b = "The party may pay within 30 days."
    flagged = compare_chunk_pair(a, b, similarity_threshold=95.0)
    assert flagged


def test_compare_flags_sentence_count_mismatch() -> None:
    a = "First sentence. Second sentence."
    b = "First sentence."
    flagged = compare_chunk_pair(a, b, similarity_threshold=95.0)
    assert flagged
    assert flagged[-1]["sentence_index"] == 1
    assert flagged[-1]["translation_1"] == "Second sentence."
    assert flagged[-1]["translation_2"] == ""


def test_protected_tokens_differ_on_numbers() -> None:
    assert protected_tokens_differ("Pay $100", "Pay $200")
    assert not protected_tokens_differ("Pay $100", "Pay $100")


def test_extract_protected_tokens() -> None:
    tokens = extract_protected_tokens("Due 01/15/2024 and 10%")
    assert tokens
