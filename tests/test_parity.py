"""Parity guards: the service must not regress quality vs the validated demo.

The strongest cheap guarantee is that the generation prompt and the system-message
assembly are byte-identical to demo/server/rag.py. (Behavioral parity on real questions
— no-self-sum, abstain, C171 — is verified by the live smoke test, not unit tests, since
it needs the upstream model.)
"""
import re
from pathlib import Path

import pytest

from app.core import prompt

DEMO_RAG = Path(__file__).resolve().parents[2] / "demo" / "server" / "rag.py"

# The demo lives outside this service dir; when it isn't checked out (e.g. CI building
# the service alone) skip the verbatim-parity check rather than fail.
_demo_missing = pytest.mark.skipif(
    not DEMO_RAG.exists(), reason="demo source not present in this checkout"
)


def _extract_demo_gen_system() -> str:
    src = DEMO_RAG.read_text(encoding="utf-8")
    m = re.search(r'GEN_SYSTEM = """(.*?)"""', src, re.DOTALL)
    assert m, "could not find GEN_SYSTEM in demo rag.py"
    return m.group(1)


@_demo_missing
def test_gen_system_matches_demo_verbatim():
    assert prompt.GEN_SYSTEM == _extract_demo_gen_system()


def test_build_system_appends_handbook_after_rules():
    sys_msg = prompt.build_system("[C1] X\nnội dung")
    assert sys_msg.startswith(prompt.GEN_SYSTEM)
    assert "TÀI LIỆU (mỗi đoạn có mã [Ck]):" in sys_msg
    assert sys_msg.rstrip().endswith("nội dung")
