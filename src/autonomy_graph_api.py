import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.autonomy_graph import refresh_autonomy_signal_graph
from src.autonomy_store import (
    create_agent_intent_qa_suite,
    get_agent_signal_graph,
    list_agent_intent_qa_suites,
)
from src.native_agents import parse_intent_suite_response, run_native_agent


router = APIRouter(prefix="/autonomy/graph")


class GraphStabilityInput(BaseModel):
    stability_seconds: int = Field(default=3600, ge=0, le=86400)


@router.get("")
def read_autonomy_graph():
    return get_agent_signal_graph()


@router.post("/refresh")
def refresh_autonomy_graph(payload: GraphStabilityInput):
    return refresh_autonomy_signal_graph(
        stability_seconds=payload.stability_seconds
    )


@router.post("/inquiry")
def generate_stable_graph_inquiry(payload: GraphStabilityInput):
    graph = refresh_autonomy_signal_graph(
        stability_seconds=payload.stability_seconds
    )
    if not graph["node_count"]:
        raise HTTPException(
            status_code=409,
            detail="The autonomy signal graph has no evidence or intent nodes yet.",
        )
    if not graph["inquiry_due"]:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "The graph has not remained unchanged long enough for a new inquiry.",
                "stable_for_seconds": graph["stable_for_seconds"],
                "required_stability_seconds": payload.stability_seconds,
                "snapshot_id": graph["snapshot_id"],
            },
        )

    context = json.dumps(
        {
            "snapshot_id": graph["snapshot_id"],
            "stable_for_seconds": graph["stable_for_seconds"],
            "nodes": graph["nodes"],
            "edges": graph["edges"],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    try:
        response = run_native_agent(
            "intent_mapper",
            (
                "Map the stable autonomy signal graph into declarative quality "
                "assurance inquiries. Preserve uncertainties as hypotheses. "
                "Return cases tied to signal IDs and do not produce executable code."
            ),
            branch_ref="autonomy/signal-graph",
            context=context,
        )
        cases = parse_intent_suite_response(response)
        suite = create_agent_intent_qa_suite(
            graph["snapshot_id"],
            cases,
            stability_seconds=payload.stability_seconds,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Intent mapper returned an invalid QA inquiry: {exc}",
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Native intent mapper could not complete the inquiry: {exc}",
        ) from exc
    return {
        "suite": suite,
        "executed": False,
        "notice": "These are declarative QA inquiries. Review and implement them as tests before treating them as executable checks.",
    }


@router.get("/intent-suites")
def read_intent_qa_suites():
    return {"suites": list_agent_intent_qa_suites()}
