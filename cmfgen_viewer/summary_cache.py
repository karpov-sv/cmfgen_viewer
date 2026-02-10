from __future__ import annotations

from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sqlite3


def _connect(db_path: str) -> sqlite3.Connection:
    path = Path(db_path).expanduser()
    connection = sqlite3.connect(str(path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    _ensure_schema(connection)
    return connection


def _ensure_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS model_summary_cache (
            model_key TEXT PRIMARY KEY,
            basepath TEXT NOT NULL,
            relpath TEXT NOT NULL,
            model_name TEXT NOT NULL,
            summary_json TEXT NOT NULL,
            vadat_mtime REAL NOT NULL,
            mod_sum_mtime REAL NOT NULL,
            summarized_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_model_summary_basepath
            ON model_summary_cache(basepath);
        """
    )


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
            ON CONFLICT(model_key) DO UPDATE SET
                basepath=excluded.basepath,
                relpath=excluded.relpath,
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
