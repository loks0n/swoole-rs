#!/usr/bin/env python3
"""Shared helpers for the coroutine gates: the repository root, the upstream pin and a
brace-matched block extractor. The ordered callback gate that lived here was deleted
(#413): its hand-written facade no longer matched either body, and the real-context
gates cover the same scheduler and channel behaviour.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tools.build_upstream import COMMIT as PIN  # noqa: E402,F401


def block(source, signature):
    start = source.index(signature)
    opening = source.index('{', start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]
