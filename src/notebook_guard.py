import json
from pathlib import Path
from typing import Any, Dict, List

DANGEROUS_PATTERNS = (
    "os.system(",
    "subprocess.",
    "eval(",
    "exec(",
    "__import__('os')",
    "__import__(\"os\")",
    "pickle.loads",
    "socket.socket",
    "open(\"/etc/passwd\"",
    "open('/etc/passwd'",
)


def _normalize_cell_source(source: Any) -> str:
    if isinstance(source, list):
        return "".join(str(item) for item in source)
    if isinstance(source, str):
        return source
    return str(source or "")


def safe_import_notebook(path: str | Path) -> Dict[str, Any]:
    path_obj = Path(path)
    payload = json.loads(path_obj.read_text(encoding="utf-8"))

    if not isinstance(payload, dict):
        raise ValueError("Notebook import failed: JSON root must be an object.")
    if "cells" not in payload or not isinstance(payload["cells"], list):
        raise ValueError("Notebook import failed: missing cells list.")

    safe_cells: List[Dict[str, Any]] = []
    for index, cell in enumerate(payload["cells"]):
        if not isinstance(cell, dict):
            continue

        source = _normalize_cell_source(cell.get("source", ""))
        flags = [pattern for pattern in DANGEROUS_PATTERNS if pattern.lower() in source.lower()]
        safe_cells.append(
            {
                "index": index,
                "cell_type": cell.get("cell_type", "code"),
                "source": source,
                "safe": not flags,
                "flags": flags,
            }
        )

    sanitized = dict(payload)
    sanitized["cells"] = safe_cells
    sanitized["safe_import"] = True
    sanitized["unsafe_cells"] = [cell["index"] for cell in safe_cells if not cell["safe"]]
    return sanitized
