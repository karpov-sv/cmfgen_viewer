from __future__ import annotations

from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sqlite3
from typing import Callable


def _connect(db_path: str) -> sqlite3.Connection:
    path = Path(db_path).expanduser()
    connection = sqlite3.connect(str(path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    _ensure_schema(connection)
    return connection


def _ensure_schema(connection: sqlite3.Connection) -> None:
    table_exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'model_summary_cache'"
    ).fetchone()
    if table_exists is None:
        _create_summary_cache_table(connection)
    else:
        table_info = connection.execute("PRAGMA table_info(model_summary_cache)").fetchall()
        primary_key_columns = [
            str(row[1])
            for row in sorted(table_info, key=lambda item: int(item[5] or 0))
            if int(row[5] or 0) > 0
        ]
        if primary_key_columns != ["basepath", "relpath"]:
            _migrate_summary_cache_primary_key(connection)
    connection.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_model_summary_basepath
            ON model_summary_cache(basepath);
        CREATE INDEX IF NOT EXISTS idx_model_summary_model_key
            ON model_summary_cache(model_key);
        """
    )


def _create_summary_cache_table(connection: sqlite3.Connection, *, table_name: str = "model_summary_cache") -> None:
    connection.execute(
        f"""
        CREATE TABLE {table_name} (
            model_key TEXT NOT NULL,
            basepath TEXT NOT NULL,
            relpath TEXT NOT NULL,
            model_name TEXT NOT NULL,
            summary_json TEXT NOT NULL,
            vadat_mtime REAL NOT NULL,
            mod_sum_mtime REAL NOT NULL,
            summarized_at TEXT NOT NULL,
            PRIMARY KEY (basepath, relpath)
        )
        """
    )


def _migrate_summary_cache_primary_key(connection: sqlite3.Connection) -> None:
    replacement = "model_summary_cache_replacement"
    connection.execute(f"DROP TABLE IF EXISTS {replacement}")
    _create_summary_cache_table(connection, table_name=replacement)
    connection.execute(
        f"""
        INSERT OR REPLACE INTO {replacement} (
            model_key, basepath, relpath, model_name,
            summary_json, vadat_mtime, mod_sum_mtime, summarized_at
        )
        SELECT
            model_key, basepath, relpath, model_name,
            summary_json, vadat_mtime, mod_sum_mtime, summarized_at
        FROM model_summary_cache
        ORDER BY summarized_at
        """
    )
    connection.execute("DROP TABLE model_summary_cache")
    connection.execute(f"ALTER TABLE {replacement} RENAME TO model_summary_cache")


def _format_cache_timestamp(timestamp: object) -> str:
    try:
        numeric = float(timestamp)
    except (TypeError, ValueError):
        return ""
    if not math.isfinite(numeric):
        return ""
    return datetime.fromtimestamp(numeric, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def upsert_model_summary(
    db_path: str,
    *,
    basepath: str,
    relpath: str,
    model_dir: Path,
    model_name: str,
    values: list[str],
    vadat_mtime: float,
    mod_sum_mtime: float,
) -> None:
    payload = json.dumps([str(value) for value in values], separators=(",", ":"))
    summarized_at = datetime.now(timezone.utc).isoformat()
    model_key = str(model_dir.expanduser().resolve())

    with _connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO model_summary_cache (
                model_key, basepath, relpath, model_name,
                summary_json, vadat_mtime, mod_sum_mtime, summarized_at
            )
            VALUES (
                :model_key, :basepath, :relpath, :model_name,
                :summary_json, :vadat_mtime, :mod_sum_mtime, :summarized_at
            )
            ON CONFLICT(basepath, relpath) DO UPDATE SET
                model_key=excluded.model_key,
                model_name=excluded.model_name,
                summary_json=excluded.summary_json,
                vadat_mtime=excluded.vadat_mtime,
                mod_sum_mtime=excluded.mod_sum_mtime,
                summarized_at=excluded.summarized_at
            """,
            {
                "model_key": model_key,
                "basepath": str(basepath),
                "relpath": str(relpath).strip("/"),
                "model_name": str(model_name),
                "summary_json": payload,
                "vadat_mtime": float(vadat_mtime),
                "mod_sum_mtime": float(mod_sum_mtime),
                "summarized_at": summarized_at,
            },
        )
        connection.commit()


def list_model_summaries(
    db_path: str,
    *,
    basepath: str,
    expected_columns: int,
) -> list[dict[str, object]]:
    with _connect(db_path) as connection:
        rows = connection.execute(
            """
            SELECT model_key, relpath, model_name, summary_json, mod_sum_mtime, summarized_at
            FROM model_summary_cache
            WHERE basepath = ?
            ORDER BY lower(model_name), lower(relpath)
            """,
            (str(basepath),),
        ).fetchall()

    items: list[dict[str, object]] = []
    for row in rows:
        relpath = str(row["relpath"] or "").strip("/")
        if not relpath:
            continue

        try:
            values_raw = json.loads(str(row["summary_json"]))
        except json.JSONDecodeError:
            continue
        if not isinstance(values_raw, list):
            continue

        values = [str(value) for value in values_raw]
        if expected_columns > 0:
            if len(values) < expected_columns:
                values.extend([""] * (expected_columns - len(values)))
            elif len(values) > expected_columns:
                values = values[:expected_columns]
            if len(values) == expected_columns:
                values[-1] = _format_cache_timestamp(row["mod_sum_mtime"])

        model_name = str(row["model_name"] or "")
        if values and not values[0]:
            values[0] = model_name or Path(relpath).name

        items.append(
            {
                "values": values,
                "path": relpath,
                "model_key": str(row["model_key"] or ""),
                "summarized_at": str(row["summarized_at"] or ""),
            }
        )
    return items


def inspect_model_summary_entry(
    db_path: str,
    *,
    basepath: str,
    relpath: str,
) -> dict[str, object]:
    """Inspect one cached model without scanning the full cache namespace."""
    normalized_relpath = str(relpath).strip().strip("/") or "."
    with _connect(db_path) as connection:
        row = connection.execute(
            """
            SELECT
                model_key, relpath, model_name, vadat_mtime,
                mod_sum_mtime, summarized_at
            FROM model_summary_cache
            WHERE basepath = ? AND relpath = ?
            """,
            (str(basepath), normalized_relpath),
        ).fetchone()

    if row is None:
        return {
            "model_key": "",
            "relpath": normalized_relpath,
            "model_name": "",
            "status": "absent",
            "reason": "Model summary is not cached.",
        }
    return _inspect_model_summary_entry(
        Path(basepath).expanduser(),
        relpath=normalized_relpath,
        row=row,
    )


def list_model_summary_namespaces(db_path: str) -> list[dict[str, object]]:
    with _connect(db_path) as connection:
        rows = connection.execute(
            """
            SELECT basepath, COUNT(*) AS entry_count, MAX(summarized_at) AS last_summarized_at
            FROM model_summary_cache
            GROUP BY basepath
            ORDER BY lower(basepath)
            """
        ).fetchall()
    return [
        {
            "basepath": str(row["basepath"] or ""),
            "entry_count": int(row["entry_count"] or 0),
            "last_summarized_at": str(row["last_summarized_at"] or ""),
        }
        for row in rows
    ]


def inspect_model_summary_cache(
    db_path: str,
    *,
    basepath: str,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> dict[str, object]:
    with _connect(db_path) as connection:
        rows = connection.execute(
            """
            SELECT
                model_key, relpath, model_name, vadat_mtime,
                mod_sum_mtime, summarized_at
            FROM model_summary_cache
            WHERE basepath = ?
            ORDER BY lower(model_name), lower(relpath)
            """,
            (str(basepath),),
        ).fetchall()

    entries: list[dict[str, object]] = []
    counts = {"valid": 0, "stale": 0, "path_changed": 0, "missing": 0, "error": 0}
    total = len(rows)
    base = Path(basepath).expanduser()
    for index, row in enumerate(rows, start=1):
        relpath = str(row["relpath"] or "").strip().strip("/")
        entry = _inspect_model_summary_entry(base, relpath=relpath, row=row)
        entries.append(entry)
        status = str(entry.get("status", "error"))
        counts[status if status in counts else "error"] += 1
        if progress_callback is not None:
            progress_callback(index, total, relpath)

    return {
        "basepath": str(basepath),
        "total": total,
        "counts": counts,
        "entries": entries,
    }


def _inspect_model_summary_entry(
    base: Path,
    *,
    relpath: str,
    row: sqlite3.Row,
) -> dict[str, object]:
    entry: dict[str, object] = {
        "model_key": str(row["model_key"] or ""),
        "relpath": relpath,
        "model_name": str(row["model_name"] or ""),
        "status": "error",
        "reason": "",
    }
    rel = Path(relpath)
    if not relpath or rel.is_absolute() or any(part == ".." for part in rel.parts):
        entry["reason"] = "Cached relative path is invalid."
        return entry

    target = base.joinpath(*[part for part in rel.parts if part not in {"", "."}])
    try:
        if not target.exists() or not target.is_dir():
            entry.update(status="missing", reason="Model directory is missing.")
            return entry
        vadat = target / "VADAT"
        mod_sum = target / "MOD_SUM"
        if not vadat.is_file() or not mod_sum.is_file():
            entry.update(status="missing", reason="VADAT or MOD_SUM is missing.")
            return entry

        resolved_target = str(target.resolve())
        entry["resolved_model_key"] = resolved_target
        if resolved_target != str(row["model_key"] or ""):
            entry.update(status="path_changed", reason="Relative path now resolves to a different model directory.")
            return entry

        vadat_mtime = float(vadat.stat().st_mtime)
        mod_sum_mtime = float(mod_sum.stat().st_mtime)
        stored_vadat_mtime = float(row["vadat_mtime"] or 0.0)
        stored_mod_sum_mtime = float(row["mod_sum_mtime"] or 0.0)
        entry["vadat_mtime"] = vadat_mtime
        entry["mod_sum_mtime"] = mod_sum_mtime
        if not _mtime_matches(vadat_mtime, stored_vadat_mtime) or not _mtime_matches(
            mod_sum_mtime, stored_mod_sum_mtime
        ):
            entry.update(status="stale", reason="VADAT or MOD_SUM changed after this summary was cached.")
            return entry
    except OSError as exc:
        entry.update(status="error", reason=f"Could not inspect model files: {exc}")
        return entry

    entry.update(status="valid", reason="Cached summary matches the current model files.")
    return entry


def _mtime_matches(current: float, cached: float) -> bool:
    return (
        math.isfinite(current)
        and math.isfinite(cached)
        and math.isclose(current, cached, rel_tol=0.0, abs_tol=1e-6)
    )


def delete_model_summary_entries(db_path: str, *, basepath: str, relpaths: list[str]) -> int:
    normalized = sorted({str(item).strip().strip("/") for item in relpaths if str(item).strip().strip("/")})
    if not normalized:
        return 0
    with _connect(db_path) as connection:
        before = connection.total_changes
        connection.executemany(
            "DELETE FROM model_summary_cache WHERE basepath = ? AND relpath = ?",
            [(str(basepath), relpath) for relpath in normalized],
        )
        deleted = connection.total_changes - before
        connection.commit()
    return int(deleted)


def delete_model_summary_namespace(db_path: str, *, basepath: str) -> int:
    with _connect(db_path) as connection:
        cursor = connection.execute("DELETE FROM model_summary_cache WHERE basepath = ?", (str(basepath),))
        connection.commit()
        return max(0, int(cursor.rowcount or 0))


def delete_model_summary_namespaces_except(db_path: str, *, basepath: str) -> int:
    with _connect(db_path) as connection:
        cursor = connection.execute("DELETE FROM model_summary_cache WHERE basepath != ?", (str(basepath),))
        connection.commit()
        return max(0, int(cursor.rowcount or 0))
