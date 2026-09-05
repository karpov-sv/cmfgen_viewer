import time
from concurrent.futures import ThreadPoolExecutor

from cmfgen_viewer.app import create_app
from cmfgen_viewer.job_store import JobStore


def test_job_stores_are_app_scoped_and_snapshots_are_isolated(tmp_path):
    first = create_app(basepath=str(tmp_path))
    second = create_app(basepath=str(tmp_path))
    store = first.extensions["cmfgen_jobs"]["grid"]
    payload = {
        "job_id": "example",
        "status": "running",
        "result": {"values": [1]},
        "created_at": time.time(),
    }
    store.insert(payload)
    payload["result"]["values"].append(2)
    snapshot = store.snapshot("example")
    snapshot["result"]["values"].append(3)
    assert store.snapshot("example")["result"]["values"] == [1]
    assert (
        second.test_client().get("/uploads/fit-grid/status/example").status_code == 404
    )
    assert (
        second.test_client().post("/uploads/fit-grid/cancel/example").status_code == 404
    )
    assert not store.cancel_requested("example")
    assert store.request_cancel("example")
    assert store.cancel_requested("example")


def test_singleton_creation_is_atomic():
    store = JobStore(max_jobs=16)
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(
            executor.map(
                lambda i: store.insert(
                    {
                        "job_id": str(i),
                        "status": "running",
                        "created_at": time.time(),
                    },
                    singleton=True,
                ),
                range(24),
            )
        )
    assert len({job_id for job_id, _ in results}) == 1
    assert sum(not existing for _, existing in results) == 1


def test_pruning_expires_finished_jobs_and_preserves_running_jobs():
    store = JobStore(max_jobs=2, ttl_seconds=10)
    now = time.time()
    store.insert({"job_id": "active", "status": "running", "created_at": now - 100})
    store.insert({"job_id": "expired", "status": "completed", "finished_at": now - 11})
    assert store.snapshot("expired") is None
    for i in range(3):
        store.insert({"job_id": str(i), "status": "completed", "finished_at": now + i})
    assert {row["job_id"] for row in store.snapshots()} == {"active", "2"}
