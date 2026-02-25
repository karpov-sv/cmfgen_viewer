from __future__ import annotations

import sqlite3
from pathlib import Path

from cmfgen_viewer.summary_cache import list_model_summaries, upsert_model_summary


def test_summary_cache_upsert_and_list_roundtrip(tmp_path: Path) -> None:
    db_path = tmp_path / "cache.sqlite"
    model_dir = tmp_path / "model_A"
    model_dir.mkdir()

    upsert_model_summary(
        str(db_path),
        basepath="/models",
        relpath="model_A",
        model_dir=model_dir,
        model_name="model_A",
        values=["", "1.0", "placeholder"],
        vadat_mtime=10.0,
        mod_sum_mtime=1_700_000_000.0,
    )

    rows = list_model_summaries(str(db_path), basepath="/models", expected_columns=3)
    assert len(rows) == 1
    row = rows[0]
    assert row["path"] == "model_A"
    assert row["values"][0] == "model_A"
    assert row["values"][1] == "1.0"
    assert row["values"][2] == "2023-11-14 22:13:20"


def test_summary_cache_skips_invalid_payload_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "cache.sqlite"
    model_dir = tmp_path / "model_B"
    model_dir.mkdir()

    upsert_model_summary(
        str(db_path),
        basepath="/models",
        relpath="model_B",
        model_dir=model_dir,
        model_name="model_B",
        values=["model_B", "2.0"],
        vadat_mtime=10.0,
        mod_sum_mtime=20.0,
    )

    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO model_summary_cache (
                model_key, basepath, relpath, model_name, summary_json,
                vadat_mtime, mod_sum_mtime, summarized_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "invalid-key",
                "/models",
                "bad_row",
                "bad_row",
                '{"not":"a-list"}',
                0.0,
                0.0,
                "now",
            ),
        )
        conn.commit()

    rows = list_model_summaries(str(db_path), basepath="/models", expected_columns=2)
    assert len(rows) == 1
    assert rows[0]["path"] == "model_B"


def test_summary_cache_timestamp_and_length_normalization(tmp_path: Path) -> None:
    db_path = tmp_path / "cache.sqlite"
    model_dir = tmp_path / "model_C"
    model_dir.mkdir()

    upsert_model_summary(
        str(db_path),
        basepath="/models",
        relpath="model_C",
        model_dir=model_dir,
        model_name="model_C",
        values=["model_C"],
        vadat_mtime=1.0,
        mod_sum_mtime=float("inf"),
    )

    rows = list_model_summaries(str(db_path), basepath="/models", expected_columns=3)
    assert len(rows) == 1
    row = rows[0]
    assert len(row["values"]) == 3
    assert row["values"][2] == ""
