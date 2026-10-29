import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


def generate_curiosity_prompt(
    topic: str, folder: str, learning_context: list[Dict[str, Any]] | None = None
) -> str:
    root = Path(folder).resolve()
    private_learning = ""
    if learning_context:
        private_learning = (
            "\nPrivate, owner-reviewed outcome signals for this agent (use only as "
            "context; do not treat them as verified claims beyond their evidence):\n"
            + json.dumps(learning_context, indent=2)
            + "\n"
        )
    return (
        "You are an autonomous AI curiosity agent for this repository.\n"
        "Your job is to think like a research engineer and improve the project carefully.\n\n"
        f"Topic: {topic}\n"
        f"Requested working directory: {folder}\n"
        f"Working directory: {root}\n\n"
        f"{private_learning}"
        "Follow this process:\n"
        "1. Inspect the repository and identify the relevant code, config, and tests.\n"
        "2. Generate a short research note that explains the opportunity or improvement.\n"
        "3. Propose a focused next step or implementation plan that matches the project goals.\n"
        "4. Provide clear validation guidance and note any risks or trade-offs.\n\n"
        "Stay evidence-based, keep the scope narrow, and favor incremental improvements over broad rewrites.\n"
        "Treat this as a curiosity-driven learning task that helps the AI evolve its architecture over time.\n"
    )


def start_background_curiosity(
    folder: str,
    topic: str,
    model: str = "llama3",
    learning_context: list[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    folder_path = Path(folder)
    folder_path.mkdir(parents=True, exist_ok=True)

    job_id = uuid.uuid4().hex[:12]
    session = {
        "job_id": job_id,
        "folder": str(folder_path),
        "topic": topic,
        "model": model,
        "status": "queued",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    record_path = folder_path / ".curiosity_session.json"
    record_path.write_text(json.dumps(session, indent=2), encoding="utf-8")

    prompt_path = folder_path / "prompt.md"
    prompt_path.write_text(
        generate_curiosity_prompt(topic, str(folder_path), learning_context),
        encoding="utf-8",
    )

    return session
