from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from .mod_sum import parse_mod_sum
from .obsflux import parse_obsflux
from .rvtj import parse_rvtj

PARSERS = {
    "RVTJ": parse_rvtj,
    "OBSFLUX": parse_obsflux,
    "MOD_SUM": parse_mod_sum,
}

MAX_PARSE_FILE_BYTES = 256 * 1024 * 1024


@lru_cache(maxsize=64)
def _parse_cached(path_str: str, mtime_ns: int, size: int) -> dict[str, object] | None:
    path = Path(path_str)
    parser = PARSERS.get(path.name.upper())
    if parser is None:
        return None
    if size > MAX_PARSE_FILE_BYTES:
        return {
            "parser": path.name.upper(),
            "title": f"{path.name} parsed view",
            "summary_table": {
                "title": "Parser",
                "columns": ["Field", "Value"],
                "rows": [["status", "skipped"], ["reason", f"file is larger than {MAX_PARSE_FILE_BYTES} bytes"]],
            },
            "tables": [],
            "plots": [],
            "warnings": [],
        }
    return parser(path)


def parse_known_file(path: Path) -> dict[str, object] | None:
    stat = path.stat()
    return _parse_cached(str(path), stat.st_mtime_ns, stat.st_size)
