from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


def ingest_web_inspiration(base_dir: str, topic: str, sources: List[str] | None = None) -> List[Dict[str, Any]]:
    root = Path(base_dir)
    inspiration_dir = root / "web_inspiration"
    inspiration_dir.mkdir(parents=True, exist_ok=True)

    sources = sources or []
    entries: List[Dict[str, Any]] = []
    for index, source in enumerate(sources, start=1):
        record = {
            "id": f"source-{index}",
            "topic": topic,
            "source": source,
            "summary": f"Research note for {topic} from {source}",
            "collected_at": datetime.now(timezone.utc).isoformat(),
        }
        entries.append(record)

    source_file = inspiration_dir / "sources.json"
    source_file.write_text("[]", encoding="utf-8")
    if entries:
        source_file.write_text(str(entries).replace("'", '"'), encoding="utf-8")

    return entries
