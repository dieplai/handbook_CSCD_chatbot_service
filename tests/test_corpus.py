"""Corpus loading, full-context builder, [Ck] map, and citation parsing.

Ported verbatim-in-behavior from demo/server/rag.py + the frontend range-citation
fix in AnswerText.tsx. No sys.path into experiments/ — the service is self-contained.
"""
from pathlib import Path

from app.core import corpus

DATA = Path(__file__).resolve().parents[1] / "data"


def test_load_chunks_returns_173():
    chunks = corpus.load_chunks(DATA)
    assert len(chunks) == 173


def test_supplement_appended_last_so_indices_stable():
    # C171-173 are the OCR image supplements; they must be the final 3 so existing
    # [Ck] indices never shift.
    chunks = corpus.load_chunks(DATA)
    cmap = corpus.build_ck_map(chunks)
    assert set(cmap) >= {"C171", "C172", "C173"}
    assert "C174" not in cmap


def test_build_full_context_has_one_anchor_per_chunk():
    chunks = corpus.load_chunks(DATA)
    ctx = corpus.build_full_context(chunks)
    assert ctx.count("[C1]") == 1
    assert "[C173]" in ctx


def test_ck_map_entry_shape():
    chunks = corpus.load_chunks(DATA)
    cmap = corpus.build_ck_map(chunks)
    entry = cmap["C1"]
    assert set(entry) == {"section", "section_full", "anchors", "text"}
    assert isinstance(entry["anchors"], list)
    assert entry["text"]


def test_parse_citations_single():
    assert corpus.parse_citations("Điều này đúng [C45].") == ["C45"]


def test_parse_citations_multiple_distinct():
    assert corpus.parse_citations("A [C3] B [C7] C [C3]") == ["C3", "C7"]


def test_parse_citations_range_enumerates_span():
    assert corpus.parse_citations("Xem [C138-C147].") == [
        f"C{i}" for i in range(138, 148)
    ]


def test_parse_citations_range_en_dash():
    assert corpus.parse_citations("Xem [C85–C89].") == ["C85", "C86", "C87", "C88", "C89"]


def test_parse_citations_range_reversed_order():
    # generator sometimes emits hi-lo; normalize to ascending span
    assert corpus.parse_citations("[C89-C85]") == ["C85", "C86", "C87", "C88", "C89"]


def test_parse_citations_range_without_second_c():
    assert corpus.parse_citations("[C10-12]") == ["C10", "C11", "C12"]


def test_parse_citations_none():
    assert corpus.parse_citations("Không có trích dẫn nào.") == []
