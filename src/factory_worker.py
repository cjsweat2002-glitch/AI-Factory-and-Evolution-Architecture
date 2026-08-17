import asyncio
import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import httpx
import yaml


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


def _get_worker_url() -> str:
    """Get the first available AI worker URL."""
    env_worker_url = os.getenv("AI_FACTORY_WORKER_URL")
    if env_worker_url:
        return env_worker_url
    
    config_path = Path("config/nodes.yaml")
    if config_path.exists():
        with open(config_path, "r") as f:
            data = yaml.safe_load(f) or {}
            nodes = data.get("nodes", [])
            if nodes:
                return nodes[0]["url"]
    
    return "http://localhost:11434"


def _run_curiosity_task(job_id: str, folder: str, topic: str, model: str) -> None:
    """Background thread function to run curiosity task against AI worker."""
    root = Path(folder)
    
    try:
        prompt_path = root / "prompt.md"
        if not prompt_path.exists():
            raise FileNotFoundError(f"Prompt file not found at {prompt_path}")
        
        prompt = prompt_path.read_text(encoding="utf-8")
        worker_url = _get_worker_url()
        target_url = f"{worker_url}/v1/chat/completions"
        
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        }
        
        # Use synchronous httpx client
        response = httpx.post(target_url, json=payload, timeout=60.0)
        response.raise_for_status()
        data = response.json()
        result = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        
        if not result:
            result = "No response from AI worker."
        
        # Update job with result
        job = {
            "job_id": job_id,
            "folder": str(root),
            "topic": topic,
            "model": model,
            "status": "completed",
            "created_at": None,  # Will be read from existing record
            "result": result,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
        
        # Save result to output file
        output_path = root / "output.md"
        output_path.write_text(f"# Curiosity Result: {topic}\n\n{result}", encoding="utf-8")
        
        # Update jobs list
        jobs = list_background_jobs(str(root))
        # Find and update the job, preserving created_at
        for j in jobs:
            if j.get("job_id") == job_id:
                job["created_at"] = j.get("created_at")
                break
        
        jobs = [j for j in jobs if j.get("job_id") != job_id]
        jobs.append(job)
        _save_jobs(str(root), jobs)
        
    except Exception as e:
        # Update job with error
        jobs = list_background_jobs(str(root))
        for j in jobs:
            if j.get("job_id") == job_id:
                j["status"] = "failed"
                j["result"] = f"Failed to run curiosity: {str(e)}"
                j["error"] = str(e)
                j["completed_at"] = datetime.now(timezone.utc).isoformat()
                break
        _save_jobs(str(root), jobs)


def run_background_job(folder: str, topic: str, model: str = "llama3") -> Dict[str, Any]:
    root = Path(folder)
    root.mkdir(parents=True, exist_ok=True)

    job_id = uuid.uuid4().hex[:12]
    job = {
        "job_id": job_id,
        "folder": str(root),
        "topic": topic,
        "model": model,
        "status": "running",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "result": "Curiosity task is running…",
    }

    # Save job with "running" status
    jobs = list_background_jobs(str(root))
    jobs.append(job)
    _save_jobs(str(root), jobs)

    # Start background thread to run curiosity task
    thread = threading.Thread(
        target=_run_curiosity_task,
        args=(job_id, str(root), topic, model),
        daemon=True
    )
    thread.start()

    return job
