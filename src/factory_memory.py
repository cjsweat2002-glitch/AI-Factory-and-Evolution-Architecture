import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


def log_repo_memory(base_dir: str, title: str, summary: str) -> Dict[str, Any]:
    root = Path(base_dir)
    memory_dir = root / "repo_memory"
    memory_dir.mkdir(parents=True, exist_ok=True)

    record = {
        "title": title,
        "summary": summary,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    doc_path = memory_dir / "decisions.md"
    existing = []
    if doc_path.exists():
        existing = doc_path.read_text(encoding="utf-8").splitlines()

    lines = list(existing)
    lines.append("")
    lines.append(f"## {title}")
    lines.append(f"- Created: {record['created_at']}")
    lines.append(f"- Summary: {summary}")
    doc_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    return record
