from __future__ import annotations

from pathlib import Path
import re

DIRECT_INFO_VALUE_RE = re.compile(
    r"^\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)(?:\s+(\d+)\s+([TF]))?\s*$",
    re.IGNORECASE,
)


def _read_info(path: Path) -> dict[str, object] | None:
    if not path.is_file():
        return None
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    for line in lines:
        match = DIRECT_INFO_VALUE_RE.match(line)
        if not match:
            continue
        nd, recl, word_size, unit_size, int_size, little_endian = match.groups()
        return {
            "nd": int(nd),
            "recl": int(recl),
            "word_size": int(word_size),
            "unit_size": int(unit_size),
            "int_size": int(int_size) if int_size is not None else None,
            "little_endian": little_endian.upper() == "T" if little_endian is not None else None,
            "info_lines": lines,
        }
    return None


def parse_direct_access_file(path: Path) -> dict[str, object]:
    info_path = path.with_name(f"{path.name}_INFO")
    metadata = _read_info(info_path)
    warnings: list[str] = []
    rows: list[list[str]] = [
        ["file", path.name],
        ["size_bytes", str(path.stat().st_size)],
        ["sidecar", info_path.name if info_path.is_file() else "missing"],
    ]
    if metadata is None:
        warnings.append("No readable direct-access _INFO sidecar was found; binary records were not decoded.")
    else:
        record_bytes = int(metadata["recl"]) * int(metadata["unit_size"])
        rows.extend(
            [
                ["depth_points", str(metadata["nd"])],
                ["record_length_units", str(metadata["recl"])],
                ["record_length_bytes", str(record_bytes)],
                ["word_size_bytes", str(metadata["word_size"])],
                ["integer_size_bytes", str(metadata["int_size"]) if metadata["int_size"] is not None else "not recorded"],
                ["byte_order", "little endian" if metadata["little_endian"] is True else "big endian" if metadata["little_endian"] is False else "not recorded"],
                ["complete_records_from_size", str(path.stat().st_size // record_bytes) if record_bytes else "n/a"],
            ]
        )
        if record_bytes and path.stat().st_size % record_bytes:
            warnings.append("File size is not an exact multiple of the sidecar record length.")

    return {
        "parser": "DIRECT_ACCESS_INFO",
        "title": f"{path.name} binary metadata",
        "summary_table": {"title": "Binary layout", "columns": ["Field", "Value"], "rows": rows},
        "tables": [],
        "plots": [],
        "warnings": warnings,
    }


def parse_direct_info(path: Path) -> dict[str, object]:
    metadata = _read_info(path)
    if metadata is None:
        rows = [[str(index), line] for index, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1)]
        return {
            "parser": "DIRECT_ACCESS_INFO",
            "title": f"{path.name} metadata",
            "summary_table": {"title": "Metadata", "columns": ["Field", "Value"], "rows": [["file", path.name]]},
            "tables": [{"title": "Contents", "columns": ["Line", "Content"], "rows": rows}],
            "plots": [],
            "warnings": ["The sidecar does not use the recognized CMFGEN direct-access layout."],
        }
    rows = [
        ["file", path.name],
        ["depth_points", str(metadata["nd"])],
        ["record_length_units", str(metadata["recl"])],
        ["word_size_bytes", str(metadata["word_size"])],
        ["unit_size_bytes", str(metadata["unit_size"])],
        ["integer_size_bytes", str(metadata["int_size"]) if metadata["int_size"] is not None else "not recorded"],
        ["byte_order", "little endian" if metadata["little_endian"] is True else "big endian" if metadata["little_endian"] is False else "not recorded"],
    ]
    return {
        "parser": "DIRECT_ACCESS_INFO",
        "title": f"{path.name} direct-access metadata",
        "summary_table": {"title": "Binary layout", "columns": ["Field", "Value"], "rows": rows},
        "tables": [],
        "plots": [],
        "warnings": [],
    }
