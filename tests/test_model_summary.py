import json
import sqlite3

from cmfgen_viewer.grid_catalog import _cmfgen_fit_params_from_summary
from cmfgen_viewer.model_summary import (
    ModelSummary,
    summary_from_model,
    summary_table_row,
)
from cmfgen_viewer.summary_cache import list_model_summaries, upsert_model_summary


def test_summary_cache_keeps_precision_and_ignores_display_order(tmp_path, monkeypatch):
    db = str(tmp_path / "cache.sqlite")
    summary = summary_from_model(
        {
            "name": "model",
            "vadat": {"LSTAR": "123456.789123456"},
            "params": {"Teff(K)": 35000.12345678, "Log_g": 3.7123456789},
        }
    )
    upsert_model_summary(
        db,
        basepath=str(tmp_path),
        relpath="model",
        model_dir=tmp_path / "model",
        model_name="model",
        summary=summary,
        vadat_mtime=1.0,
        mod_sum_mtime=2.0,
    )
    monkeypatch.setattr(
        "cmfgen_viewer.model_summary.SUMMARY_COLUMNS",
        ["logg", "MODEL", "T_2/3", "LSTAR"],
    )
    cached = list_model_summaries(db, basepath=str(tmp_path))[0]["summary"]
    assert cached == summary
    assert summary_table_row(cached)[1] == "model"
    assert _cmfgen_fit_params_from_summary(cached) == {
        "teff_k": 35000.12345678,
        "log_g": 3.7123456789,
        "luminosity": 123456.789123456,
    }
    with sqlite3.connect(db) as connection:
        payload = json.loads(
            connection.execute(
                "SELECT summary_json FROM model_summary_cache"
            ).fetchone()[0]
        )
    assert payload["schema_version"] == 1
    assert payload["fields"]["luminosity"] == 123456.789123456


def test_legacy_cache_migration_uses_historical_field_order(tmp_path, monkeypatch):
    db = str(tmp_path / "cache.sqlite")
    upsert_model_summary(
        db,
        basepath="/models",
        relpath="old",
        model_dir=tmp_path,
        model_name="old",
        summary=ModelSummary(name="old"),
        vadat_mtime=1.0,
        mod_sum_mtime=2.0,
    )
    with sqlite3.connect(db) as connection:
        connection.execute(
            "UPDATE model_summary_cache SET summary_json = ?",
            (json.dumps(["old", "1.2345D+5", "1.0-6"]),),
        )
        connection.execute("PRAGMA user_version=0")
    monkeypatch.setattr(
        "cmfgen_viewer.model_summary.SUMMARY_COLUMNS", ["MDOT", "MODEL", "LSTAR"]
    )
    summary = list_model_summaries(db, basepath="/models")[0]["summary"]
    assert summary == ModelSummary(name="old", luminosity=123450.0, mass_loss_rate=1e-6)
    with sqlite3.connect(db) as connection:
        payload = json.loads(
            connection.execute(
                "SELECT summary_json FROM model_summary_cache"
            ).fetchone()[0]
        )
    assert payload["fields"]["name"] == "old"
