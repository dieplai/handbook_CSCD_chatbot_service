"""Corpus: load chunks, build the full-context prompt block, the [Ck] map, and
parse citation codes (single + range) out of generated answers.

Behavior ported from the validated demo (demo/server/rag.py: build_full_context,
ck_map) and the frontend range-citation fix (AnswerText.tsx regex). Self-contained:
chunks are read from the local data/ dir, no experiments/ on sys.path.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

# 170 base rule-aware chunks + 3 OCR image supplements (C171-173: 6 điều Bác Hồ,
# 5 lời thề, Tư cách CA). Supplement is appended LAST so existing [Ck] indices stay
# stable — never reorder these two reads.
_BASE = "chunks_v3_precise_rules.jsonl"
_SUPPLEMENT = "supplementary_chunks.jsonl"

# Matches [C45] and ranges [C138-C147] / [C85–C89] (en-dash) / [C10-12] (no 2nd C).
_CITE_RE = re.compile(r"\[C(\d+)(?:\s*[-–]\s*C?(\d+))?\]")


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def load_chunks(data_dir: Path) -> list[dict]:
    chunks = read_jsonl(data_dir / _BASE)
    supp = data_dir / _SUPPLEMENT
    if supp.exists():
        chunks += read_jsonl(supp)
    return chunks


def _body(text: str) -> str:
    """Strip a leading '[...]' label the chunk text may carry, matching the demo."""
    return text.split("]", 1)[-1].strip() if text.startswith("[") else text


def build_full_context(chunks: list[dict]) -> str:
    """Whole handbook in reading order, one [Ck] anchor per chunk."""
    parts = []
    for idx, c in enumerate(chunks, 1):
        section = " > ".join(c.get("section_path", [])[-3:])
        parts.append(f"[C{idx}] {section}\n{_body(c['text'])}")
    return "\n\n".join(parts)


def build_ck_map(chunks: list[dict]) -> dict[str, dict]:
    """1-based [Ck] -> {section, section_full, anchors, text}, matching
    build_full_context ordering so a citation maps to the exact passage."""
    out: dict[str, dict] = {}
    for idx, c in enumerate(chunks, 1):
        path = c.get("section_path", [])
        out[f"C{idx}"] = {
            "section": " > ".join(path[-3:]),
            "section_full": " > ".join(path),
            "anchors": c.get("block_ids", []) or c.get("anchors", []),
            "text": _body(c["text"]),
        }
    return out


def parse_citations(answer: str) -> list[str]:
    """Citation codes referenced by an answer, in first-seen order, ranges expanded.
    [C138-C147] -> C138..C147; handles en-dash and reversed (hi-lo) spans."""
    seen: set[int] = set()
    ordered: list[str] = []
    for lo_s, hi_s in _CITE_RE.findall(answer):
        lo = int(lo_s)
        hi = int(hi_s) if hi_s else lo
        if hi < lo:
            lo, hi = hi, lo
        for n in range(lo, hi + 1):
            if n not in seen:
                seen.add(n)
                ordered.append(f"C{n}")
    return ordered
