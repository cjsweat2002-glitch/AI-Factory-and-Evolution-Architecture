import json
import math
import re
from typing import Any, Dict, Iterable, List


_TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]+", re.IGNORECASE)
_STOP_WORDS = {
    "about",
    "after",
    "also",
    "among",
    "and",
    "are",
    "because",
    "before",
    "between",
    "does",
    "from",
    "have",
    "into",
    "more",
    "only",
    "than",
    "that",
    "their",
    "this",
    "through",
    "under",
    "what",
    "when",
    "where",
    "which",
    "with",
}

_COMPACT_KEYS = {
    "domain": "d",
    "claim": "c",
    "evidence_type": "e",
    "source_ref": "s",
    "observation": "o",
    "interpretation": "i",
    "competing_explanation": "x",
    "discriminating_test": "t",
    "limitations": "l",
    "reviewer_note": "v",
}

_EVIDENCE_WEIGHT = {
    "published_measurement": 6,
    "reproduced_result": 5,
    "calculation": 4,
    "model_result": 3,
    "interpretation": 2,
    "hypothesis": 1,
}
_EVIDENCE_TYPES = {
    "published_measurement",
    "reproduced_result",
    "calculation",
    "model_result",
    "interpretation",
    "hypothesis",
}


def _tokens(text: str) -> set[str]:
    return {
        token.lower()
        for token in _TOKEN_PATTERN.findall(text)
        if token.lower() not in _STOP_WORDS
    }


def _compact_record(finding: Dict[str, Any]) -> Dict[str, str]:
    return {
        compact_key: str(finding.get(field, ""))
        for field, compact_key in _COMPACT_KEYS.items()
        if finding.get(field)
    }


def _relevance(finding: Dict[str, Any], query_tokens: set[str]) -> int:
    searchable = " ".join(
        str(finding.get(field, ""))
        for field in ("domain", "claim", "observation", "interpretation")
    )
    overlap = len(query_tokens & _tokens(searchable))
    return overlap * 10 + _EVIDENCE_WEIGHT.get(finding.get("evidence_type"), 0)


def build_research_memory_context(
    objective: str,
    findings: Iterable[Dict[str, Any]],
    *,
    max_chars: int = 8000,
) -> Dict[str, Any]:
    """Select verified evidence and encode it losslessly with compact field keys."""
    if not isinstance(objective, str) or not objective.strip():
        raise ValueError("research memory objective is required")
    if isinstance(max_chars, bool) or not isinstance(max_chars, int) or max_chars < 1:
        raise ValueError("research memory character budget must be a positive integer")

    verified = [finding for finding in findings if finding.get("status") == "verified"]
    query_tokens = _tokens(objective)
    ranked = sorted(
        verified,
        key=lambda finding: (
            _relevance(finding, query_tokens),
            str(finding.get("reviewed_at") or finding.get("created_at") or ""),
            str(finding.get("id") or ""),
        ),
        reverse=True,
    )

    selected: List[Dict[str, str]] = []
    compact_lines: List[str] = []
    verbose_records: List[Dict[str, str]] = []
    char_count = 0
    for finding in ranked:
        compact = _compact_record(finding)
        line = json.dumps(compact, ensure_ascii=False, separators=(",", ":"))
        separator_chars = 1 if compact_lines else 0
        if char_count + separator_chars + len(line) > max_chars:
            continue
        selected.append(compact)
        compact_lines.append(line)
        char_count += separator_chars + len(line)
        verbose_records.append(
            {
                field: str(finding.get(field, ""))
                for field in _COMPACT_KEYS
                if finding.get(field)
            }
        )

    compact_context = "\n".join(compact_lines)
    verbose_context = json.dumps(
        verbose_records, ensure_ascii=False, separators=(",", ":")
    )
    verbose_chars = len(verbose_context) if verbose_records else 0
    compact_chars = len(compact_context)
    return {
        "context": compact_context,
        "metrics": {
            "verified_findings": len(verified),
            "selected_findings": len(selected),
            "omitted_findings": len(verified) - len(selected),
            "verbose_chars": verbose_chars,
            "compact_chars": compact_chars,
            "compression_ratio": (
                round(compact_chars / verbose_chars, 4) if verbose_chars else 1.0
            ),
            "space_savings_percent": (
                round(100 * (1 - compact_chars / verbose_chars), 2)
                if verbose_chars
                else 0.0
            ),
            "estimated_tokens": math.ceil(compact_chars / 4),
            "findings_per_1000_chars": (
                round(len(selected) * 1000 / compact_chars, 2)
                if compact_chars
                else 0.0
            ),
        },
    }


def parse_research_finding_response(
    response: str, *, domain: str, source_ref: str
) -> Dict[str, str]:
    try:
        decoded = json.loads(response)
    except json.JSONDecodeError as exc:
        raise ValueError("native researcher response must be JSON") from exc
    if not isinstance(decoded, dict):
        raise ValueError("native researcher response must be an object")

    fields = {
        "claim": decoded.get("claim"),
        "evidence_type": decoded.get("evidence_type"),
        "observation": decoded.get("observation"),
        "interpretation": decoded.get("interpretation"),
        "competing_explanation": decoded.get("competing_explanation"),
        "discriminating_test": decoded.get("discriminating_test"),
        "limitations": decoded.get("limitations"),
    }
    if any(not isinstance(value, str) or not value.strip() for value in fields.values()):
        raise ValueError("native researcher response omitted a required finding field")
    if fields["evidence_type"] not in _EVIDENCE_TYPES:
        raise ValueError("native researcher returned an unsupported evidence type")

    limits = {
        "claim": 1000,
        "observation": 2000,
        "interpretation": 2000,
        "competing_explanation": 2000,
        "discriminating_test": 2000,
        "limitations": 2000,
    }
    if any(len(fields[name].strip()) > limit for name, limit in limits.items()):
        raise ValueError("native researcher response exceeded a finding field limit")
    if not isinstance(domain, str) or not domain.strip() or len(domain.strip()) > 120:
        raise ValueError("research domain is invalid")
    if not isinstance(source_ref, str) or not source_ref.strip() or len(source_ref.strip()) > 1000:
        raise ValueError("research source reference is invalid")

    return {
        "domain": domain.strip(),
        **{name: value.strip() for name, value in fields.items()},
        "source_ref": source_ref.strip(),
    }
