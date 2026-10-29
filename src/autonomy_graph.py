import uuid
from collections import defaultdict
from typing import Any, Dict, Iterable, List

from src.autonomy_store import (
    list_agent_authorities,
    list_agent_issue_drafts,
    list_agent_research_findings,
    list_agent_cycles,
    list_outcomes,
    persist_agent_signal_graph,
)


_RESEARCH_SALIENCE = {
    "published_measurement": 0.95,
    "reproduced_result": 0.85,
    "calculation": 0.75,
    "model_result": 0.6,
    "interpretation": 0.4,
    "hypothesis": 0.2,
}


def _node_id(source_type: str, source_id: str) -> str:
    return uuid.uuid5(
        uuid.NAMESPACE_URL, f"ai-factory-signal:{source_type}:{source_id}"
    ).hex


def _bounded_salience(value: float) -> float:
    return min(1.0, max(0.0, value))


def _build_nodes(
    *,
    authorities: Iterable[Dict[str, Any]],
    issues: Iterable[Dict[str, Any]],
    findings: Iterable[Dict[str, Any]],
    outcomes: Iterable[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    nodes = []
    for authority in authorities:
        status = authority["status"]
        if status == "promotion_ready":
            signal_type = "validated_success"
            salience = _bounded_salience(abs(authority.get("actual_gain") or 0))
        elif status == "rejected":
            signal_type = "rejected_change"
            salience = _bounded_salience(abs(authority.get("actual_gain") or 0))
        elif status == "active":
            signal_type = "uncertainty" if authority["confidence"] < 0.75 else "active_intent"
            salience = _bounded_salience(
                1 - authority["confidence"]
                if signal_type == "uncertainty"
                else authority["confidence"]
            )
        else:
            continue

        node_id = _node_id("authority", authority["id"])
        evidence = authority.get("gate_evidence") or authority.get("proposal_evidence") or ""
        nodes.append(
            {
                "id": node_id,
                "source_type": "authority",
                "source_id": authority["id"],
                "cycle_id": authority["cycle_id"],
                "authority_id": authority["id"],
                "domain": authority["axis"],
                "signal_type": signal_type,
                "salience": salience,
                "summary": f"{authority['objective']} {evidence}".strip()[:4000],
                "source_ref": authority["branch_ref"],
                "created_at": authority["created_at"],
            }
        )

    for issue in issues:
        node_id = _node_id("issue", issue["id"])
        nodes.append(
            {
                "id": node_id,
                "source_type": "issue",
                "source_id": issue["id"],
                "cycle_id": None,
                "authority_id": None,
                "domain": issue["axis"],
                "signal_type": "candidate_intent",
                "salience": 0.2,
                "summary": f"{issue['title']}: {issue['body']}"[:4000],
                "source_ref": f"issue-draft:{issue['id']}",
                "created_at": issue["created_at"],
            }
        )

    for finding in findings:
        verified = finding["status"] == "verified"
        node_id = _node_id("research", finding["id"])
        evidence_type = finding["evidence_type"]
        if verified:
            signal_type = "validated_insight"
            salience = _RESEARCH_SALIENCE.get(evidence_type, 0.1)
            summary = finding["claim"]
        elif finding["status"] == "contradicted":
            signal_type = "contradicted_claim"
            salience = 0.5
            summary = f"Contradicted: {finding['claim']}"
        else:
            signal_type = "unverified_hypothesis"
            salience = 0.15
            summary = f"Unverified: {finding['claim']}"
        nodes.append(
            {
                "id": node_id,
                "source_type": "research",
                "source_id": finding["id"],
                "cycle_id": finding["cycle_id"],
                "authority_id": finding["authority_id"],
                "domain": finding["domain"],
                "signal_type": signal_type,
                "salience": salience,
                "summary": summary[:4000],
                "source_ref": finding["source_ref"],
                "created_at": finding["created_at"],
            }
        )

    for outcome in outcomes:
        if outcome["status"] != "verified":
            continue
        deviation = outcome["net_deviation_percent"]
        node_id = _node_id("outcome", outcome["id"])
        nodes.append(
            {
                "id": node_id,
                "source_type": "outcome",
                "source_id": outcome["id"],
                "cycle_id": None,
                "authority_id": None,
                "domain": outcome["metric"],
                "signal_type": (
                    "measured_gain" if deviation > 0 else "measured_regression"
                ),
                "salience": _bounded_salience(abs(deviation) / 100),
                "summary": (
                    f"{outcome['metric']}: {outcome['baseline']} to "
                    f"{outcome['observed']} {outcome['unit']} "
                    f"({deviation:.2f} normalized percentage points)"
                ),
                "source_ref": f"verified-outcome:{outcome['id']}",
                "created_at": outcome["created_at"],
            }
        )

    return nodes


def _build_edges(
    nodes: List[Dict[str, Any]],
    authorities: Iterable[Dict[str, Any]],
    cycles: Iterable[Dict[str, Any]],
    issues: Iterable[Dict[str, Any]],
    findings: Iterable[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    edges = []
    seen = set()

    def connect(source: str, target: str, relation: str, weight: float) -> None:
        key = (source, target, relation)
        if source != target and key not in seen:
            edges.append(
                {
                    "source_id": source,
                    "target_id": target,
                    "relation": relation,
                    "weight": weight,
                }
            )
            seen.add(key)

    by_domain: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    by_cycle: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    node_by_authority: Dict[str, str] = {}
    node_by_source = {
        (node["source_type"], node["source_id"]): node["id"] for node in nodes
    }
    for node in nodes:
        by_domain[node["domain"]].append(node)
        if node["cycle_id"]:
            by_cycle[node["cycle_id"]].append(node)
        if node["source_type"] == "authority" and node["authority_id"]:
            node_by_authority[node["authority_id"]] = node["id"]

    for related_nodes in (*by_domain.values(), *by_cycle.values()):
        related_nodes.sort(key=lambda node: (node["created_at"], node["id"]))
        for previous, current in zip(related_nodes, related_nodes[1:]):
            relation = (
                "same_cycle"
                if previous["cycle_id"]
                and previous["cycle_id"] == current["cycle_id"]
                else "shared_dimension"
            )
            connect(
                previous["id"],
                current["id"],
                relation,
                min(previous["salience"], current["salience"]),
            )

    for finding in findings:
        authority_node = node_by_authority.get(finding["authority_id"])
        finding_node = node_by_source.get(("research", finding["id"]))
        if authority_node and finding_node:
            connect(finding_node, authority_node, "evidence_for", 0.9)

    issue_node_ids = {
        issue["id"]: node_by_source.get(("issue", issue["id"])) for issue in issues
    }
    source_issues = {
        cycle["id"]: cycle.get("source_issue") for cycle in cycles
    }
    for authority in authorities:
        if authority["parent_id"] is None:
            issue_id = source_issues.get(authority["cycle_id"])
            issue_node = issue_node_ids.get(issue_id)
            authority_node = node_by_authority.get(authority["id"])
            if issue_node and authority_node:
                connect(issue_node, authority_node, "intent_source", 1.0)

    return edges


def refresh_autonomy_signal_graph(*, stability_seconds: int = 3600) -> Dict[str, Any]:
    authorities = list_agent_authorities(limit=5000)
    cycles = list_agent_cycles(limit=5000)
    issues = list_agent_issue_drafts()
    findings = list_agent_research_findings(limit=1000)
    outcomes = list_outcomes()
    nodes = _build_nodes(
        authorities=authorities,
        issues=issues,
        findings=findings,
        outcomes=outcomes,
    )
    edges = _build_edges(nodes, authorities, cycles, issues, findings)
    snapshot = persist_agent_signal_graph(
        nodes,
        edges,
        stability_seconds=stability_seconds,
    )
    return {**snapshot, "nodes": nodes, "edges": edges}
