import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


def _job_state_path(base_dir: str) -> Path:
    root = Path(base_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root / ".background_jobs.json"


def list_background_jobs(base_dir: str) -> List[Dict[str, Any]]:
    state_path = _job_state_path(base_dir)
    if not state_path.exists():
        return []
    try:
        jobs = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return jobs if isinstance(jobs, list) else []


def _save_jobs(base_dir: str, jobs: List[Dict[str, Any]]) -> None:
    state_path = _job_state_path(base_dir)
    state_path.write_text(json.dumps(jobs, indent=2), encoding="utf-8")


def run_background_job(folder: str, topic: str, model: str = "llama3") -> Dict[str, Any]:
    root = Path(folder)
    root.mkdir(parents=True, exist_ok=True)

    job = {
        "job_id": uuid.uuid4().hex[:12],
        "folder": str(root),
        "topic": topic,
        "model": model,
        "status": "completed",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "result": f"Curiosity task completed: {topic}",
    }

    jobs = list_background_jobs(str(root))
    jobs.append(job)
    _save_jobs(str(root), jobs)

    return job
