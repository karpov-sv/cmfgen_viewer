from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from cmfgen_viewer.summary_cache import (
    delete_model_summary_entries,
    delete_model_summary_namespace,
    delete_model_summary_namespaces_except,
    inspect_model_summary_cache,
    inspect_model_summary_entry,
    list_model_summaries,
    list_model_summary_namespaces,
    upsert_model_summary,
)


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


def test_summary_cache_inspects_one_entry_or_reports_absent(tmp_path: Path) -> None:
    db_path = tmp_path / "cache.sqlite"
    base = tmp_path / "models"
    model_dir = base / "model_A"
    model_dir.mkdir(parents=True)
    (model_dir / "VADAT").write_text("1 [LSTAR]\n", encoding="utf-8")
    (model_dir / "MOD_SUM").write_text("summary\n", encoding="utf-8")

    absent = inspect_model_summary_entry(
        str(db_path),
        basepath=str(base),
        relpath="model_A",
    )
    assert absent["status"] == "absent"

    upsert_model_summary(
        str(db_path),
        basepath=str(base),
        relpath="model_A",
        model_dir=model_dir,
        model_name="model_A",
        values=["model_A"],
        vadat_mtime=(model_dir / "VADAT").stat().st_mtime,
        mod_sum_mtime=(model_dir / "MOD_SUM").stat().st_mtime,
    )
    assert inspect_model_summary_entry(
        str(db_path),
        basepath=str(base),
        relpath="model_A",
    )["status"] == "valid"


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


def test_summary_cache_migrates_legacy_primary_key_and_keeps_base_namespaces(tmp_path: Path) -> None:
    db_path = tmp_path / "cache.sqlite"
    model_dir = tmp_path / "shared_model"
    model_dir.mkdir()
    with sqlite3.connect(str(db_path)) as connection:
        connection.execute(
            """
            CREATE TABLE model_summary_cache (
                model_key TEXT PRIMARY KEY,
                basepath TEXT NOT NULL,
                relpath TEXT NOT NULL,
                model_name TEXT NOT NULL,
                summary_json TEXT NOT NULL,
                vadat_mtime REAL NOT NULL,
                mod_sum_mtime REAL NOT NULL,
                summarized_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO model_summary_cache VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (str(model_dir), "/first", "shared", "shared", '["shared"]', 1.0, 2.0, "2025-01-01"),
        )
        connection.commit()

    assert len(list_model_summaries(str(db_path), basepath="/first", expected_columns=1)) == 1
    with sqlite3.connect(str(db_path)) as connection:
        primary_key = [
            row[1]
            for row in sorted(connection.execute("PRAGMA table_info(model_summary_cache)"), key=lambda row: row[5])
            if row[5]
        ]
    assert primary_key == ["basepath", "relpath"]

    upsert_model_summary(
        str(db_path),
        basepath="/second",
        relpath="shared",
        model_dir=model_dir,
        model_name="shared",
        values=["shared"],
        vadat_mtime=1.0,
        mod_sum_mtime=2.0,
    )
    assert {item["basepath"] for item in list_model_summary_namespaces(str(db_path))} == {"/first", "/second"}


def test_summary_cache_inspection_classifies_entries_and_cleanup(tmp_path: Path) -> None:
    db_path = tmp_path / "cache.sqlite"
    base = tmp_path / "models"
    base.mkdir()

    def add_model(name: str) -> Path:
        model = base / name
        model.mkdir()
        (model / "VADAT").write_text("1 [LSTAR]\n", encoding="utf-8")
        (model / "MOD_SUM").write_text("summary\n", encoding="utf-8")
        upsert_model_summary(
            str(db_path),
            basepath=str(base),
            relpath=name,
            model_dir=model,
            model_name=name,
            values=[name],
            vadat_mtime=(model / "VADAT").stat().st_mtime,
            mod_sum_mtime=(model / "MOD_SUM").stat().st_mtime,
        )
        return model

    add_model("valid")
    stale = add_model("stale")
    missing = add_model("missing")
    (stale / "VADAT").touch()
    stale_mtime = (stale / "VADAT").stat().st_mtime + 10.0
    (stale / "VADAT").touch()
    os.utime(stale / "VADAT", (stale_mtime, stale_mtime))
    (missing / "MOD_SUM").unlink()

    inspection = inspect_model_summary_cache(str(db_path), basepath=str(base))
    assert inspection["counts"] == {"valid": 1, "stale": 1, "path_changed": 0, "missing": 1, "error": 0}
    statuses = {item["relpath"]: item["status"] for item in inspection["entries"]}
    assert statuses == {"missing": "missing", "stale": "stale", "valid": "valid"}

    assert delete_model_summary_entries(str(db_path), basepath=str(base), relpaths=["missing"]) == 1
    assert delete_model_summary_namespace(str(db_path), basepath="/not-present") == 0
    assert delete_model_summary_namespaces_except(str(db_path), basepath=str(base)) == 0
    assert inspect_model_summary_cache(str(db_path), basepath=str(base))["total"] == 2


def test_summary_cache_inspection_allows_external_symlink_and_detects_retargeting(tmp_path: Path) -> None:
    db_path = tmp_path / "cache.sqlite"
    base = tmp_path / "models"
    targets = tmp_path / "archive"
    base.mkdir()
    targets.mkdir()
    for name in ("first", "second"):
        target = targets / name
        target.mkdir()
        (target / "VADAT").write_text("1 [LSTAR]\n", encoding="utf-8")
        (target / "MOD_SUM").write_text("summary\n", encoding="utf-8")

    linked_model = base / "linked"
    linked_model.symlink_to(targets / "first", target_is_directory=True)
    upsert_model_summary(
        str(db_path),
        basepath=str(base),
        relpath="linked",
        model_dir=linked_model,
        model_name="linked",
        values=["linked"],
        vadat_mtime=(linked_model / "VADAT").stat().st_mtime,
        mod_sum_mtime=(linked_model / "MOD_SUM").stat().st_mtime,
    )
    assert inspect_model_summary_cache(str(db_path), basepath=str(base))["counts"]["valid"] == 1

    linked_model.unlink()
    linked_model.symlink_to(targets / "second", target_is_directory=True)
    inspection = inspect_model_summary_cache(str(db_path), basepath=str(base))
    assert inspection["counts"]["path_changed"] == 1
