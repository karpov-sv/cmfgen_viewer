import pytest

from cmfgen_viewer.grid_jobs import _grid_search_job_create, _run_upload_grid_search_job
from cmfgen_viewer.job_store import JobStore


@pytest.mark.parametrize("cancel", [False, True])
@pytest.mark.parametrize("fit_source", ["cmfgen", "bosz", "phoenix"])
def test_grid_worker_uses_injected_store_without_flask_context(monkeypatch, cancel, fit_source):
    store = JobStore(max_jobs=32)
    other_store = JobStore(max_jobs=32)
    job_id = _grid_search_job_create(
        store, upload_token="ExampleToken123", fit_source=fit_source, mode="normalized",
        fit_bounds={}, fit_wavelength_range=None, model_name_pattern="", total_models=2,
    )
    fitted = []

    def fit(*, candidate, should_cancel, **kwargs):
        fitted.append(candidate["model_name"])
        if cancel:
            store.request_cancel(job_id)
            assert should_cancel()
            return {"status": "canceled"}
        return {"status": "success", "item": {"model_name": candidate["model_name"], "rmse": candidate["rmse"]}}

    monkeypatch.setattr("cmfgen_viewer.grid_jobs._fit_single_grid_candidate", fit)
    _run_upload_grid_search_job(
        store, job_id, upload_token="ExampleToken123", fit_source=fit_source, mode="normalized",
        observed={}, fit_bounds={}, fit_wavelength_range=None, model_name_pattern="",
        model_candidates=[{"model_name": "first", "rmse": 2.0}, {"model_name": "second", "rmse": 1.0}],
        lambda_min=1000, lambda_max=9000, max_pool_size=1,
    )
    snapshot = store.snapshot(job_id)
    assert other_store.snapshot(job_id) is None
    if cancel:
        assert fitted == ["first"]
        assert snapshot["status"] == "canceled"
    else:
        assert fitted == ["first", "second"]
        assert snapshot["status"] == "completed"
        assert snapshot["processed"] == snapshot["successful"] == 2
        assert snapshot["result"]["best_model"]["model_name"] == "second"
