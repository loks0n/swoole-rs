"""Shared helpers for the reactor gates: the repository root, the upstream pin and a
brace-matched block extractor. The ordered dispatch gate that lived here compared
the poll/epoll/kqueue loops and the interest methods, which are upstream's code
again (#336), so it is gone.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tools.build_hybrid import apply_patch_verified  # noqa: E402,F401  (re-exported for the gates)
from tools.build_upstream import COMMIT as PIN  # noqa: E402,F401


def block(source, start):
    opening = source.index('{', start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end], end
