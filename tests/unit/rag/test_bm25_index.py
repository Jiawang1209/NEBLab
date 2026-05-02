"""Tests for BM25Index — sparse keyword search over chunk text."""

from neblab_rag.rag.bm25_index import BM25Index, _tokenize


def test_tokenize_lowercases_and_splits_english() -> None:
    assert _tokenize("Connectivity Hypothesis in Drylands") == [
        "connectivity",
        "hypothesis",
        "in",
        "drylands",
    ]


def test_tokenize_strips_punctuation() -> None:
    assert _tokenize("desertification, climate-change!") == [
        "desertification",
        "climate",
        "change",
    ]


def test_tokenize_keeps_chinese_chars_individually() -> None:
    """CJK has no word boundaries; char-level is the standard simple
    tokenizer for BM25 over Chinese text."""
    tokens = _tokenize("沙漠化")
    assert tokens == ["沙", "漠", "化"]


def test_search_ranks_exact_match_first() -> None:
    """Larger corpus so query-term IDF stays positive — BM25 zeros out terms
    that appear in too many of the test docs (correct behavior, just an
    artifact of tiny corpora)."""
    docs = [
        (1, "Climate change drives precipitation patterns"),
        (2, "The connectivity hypothesis explains desertification spread"),
        (3, "Soil heterogeneity in arid regions"),
        (4, "Vegetation patterns in Mediterranean ecosystems"),
        (5, "Wind erosion impacts on agricultural land"),
        (6, "Carbon flux measurements in temperate grasslands"),
    ]
    idx = BM25Index.from_chunks(docs)

    results = idx.search("connectivity hypothesis", top_k=3)
    assert results[0].chunk_id == 2  # only doc with both terms — wins decisively


def test_search_filters_zero_score_chunks() -> None:
    """A chunk with no query-term overlap shouldn't appear in results.
    Sparse retrieval is precision-oriented, not recall-oriented — rerank
    handles recall."""
    docs = [
        (1, "exact match here"),
        (2, "totally unrelated bananas oranges"),
        (3, "more unrelated content about apples"),
        (4, "yet another off-topic paragraph"),
    ]
    idx = BM25Index.from_chunks(docs)
    results = idx.search("exact", top_k=10)
    assert [r.chunk_id for r in results] == [1]  # not [1, 2, 3, 4]


def test_search_returns_empty_when_no_chunks() -> None:
    idx = BM25Index.from_chunks([])
    assert idx.search("anything", top_k=5) == []


def test_search_handles_empty_query() -> None:
    docs = [(1, "some text")]
    idx = BM25Index.from_chunks(docs)
    # Empty query → no tokens → no scoring; should return [] not crash
    assert idx.search("", top_k=5) == []


def test_search_top_k_limit_respected() -> None:
    docs = [(i, f"chunk number {i} contains words") for i in range(1, 11)]
    idx = BM25Index.from_chunks(docs)
    results = idx.search("chunk", top_k=3)
    assert len(results) == 3
