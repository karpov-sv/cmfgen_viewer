"""Lossless tokenization of CMFGEN value [KEY] control rows.

Keys are normalized for lookup; spans always refer to the original text so
editors can replace a value without rewriting whitespace, comments, or keys.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

KEYWORD_ROW_RE = re.compile(r"^\s*(.*?)\s+\[([A-Za-z0-9_./+=-]+)\](?:\s*!\s*(.*))?\s*$")
# Lookup identifiers remain normalized; these native keys require mixed case.
NATIVE_VADAT_KEY_SPELLINGS = {"INCL_DSLDT": "INCL_dSLdT", "MAX_DT": "MAX_dT"}


@dataclass(frozen=True)
class ControlRow:
    key: str
    source_key: str
    key_start: int
    key_end: int
    line_index: int
    value_start: int
    value_end: int
    value: str
    comment: str


def tokenize_control(contents: str) -> list[ControlRow]:
    rows = []
    for index, line in enumerate(contents.splitlines(keepends=True)):
        if not line.strip() or line.lstrip().startswith(("!", "#")):
            continue
        match = KEYWORD_ROW_RE.match(line)
        if match is None:
            continue
        value, key, comment = match.groups()
        rows.append(
            ControlRow(
                key=key.upper(),
                source_key=key,
                key_start=match.start(2),
                key_end=match.end(2),
                line_index=index,
                value_start=match.start(1),
                value_end=match.end(1),
                value=value.strip(),
                comment=(comment or "").strip(),
            )
        )
    return rows


def control_occurrences(contents: str) -> dict[str, list[dict[str, object]]]:
    """Group active rows for duplicate checks and source-preserving edits."""
    occurrences: dict[str, list[dict[str, object]]] = {}
    for row in tokenize_control(contents):
        occurrences.setdefault(row.key, []).append(
            {**asdict(row), "line": row.line_index + 1}
        )
    return occurrences
