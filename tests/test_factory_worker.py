import json

from src import factory_worker


def test_push_failure_does_not_change_successful_job_to_failed(monkeypatch, tmp_path):
    job_id = "job-123"
    (tmp_path / "prompt.md").write_text("Research this topic.", encoding="utf-8")
    (tmp_path / ".background_jobs.json").write_text(
        json.dumps(
            [
                {
                    "job_id": job_id,
                    "status": "running",
                    "created_at": "2026-01-01T00:00:00+00:00",
                }
            ]
        ),
        encoding="utf-8",
    )

    class WorkerResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "Research complete."}}]}

    monkeypatch.setattr(factory_worker, "_get_worker_url", lambda: "http://worker")
    monkeypatch.setattr(factory_worker.httpx, "post", lambda *args, **kwargs: WorkerResponse())

    def fail_notification(*args, **kwargs):
        raise RuntimeError("push endpoint unavailable")

    monkeypatch.setattr(factory_worker, "send_push_notification", fail_notification)

    factory_worker._run_curiosity_task(job_id, str(tmp_path), "topic", "model")

    jobs = factory_worker.list_background_jobs(str(tmp_path))
    assert jobs[0]["status"] == "completed"
    assert jobs[0]["result"] == "Research complete."
