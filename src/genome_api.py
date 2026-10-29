from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.autonomy_store import (
    apply_universal_genome_change,
    evolve_agent_genome,
    get_agent_genome,
    list_agent_genomes,
)


router = APIRouter(prefix="/autonomy")


class GenomeEvolutionInput(BaseModel):
    capability: Literal[
        "global_skills",
        "research",
        "code_development",
        "engine_development",
        "web_research",
    ]
    evidence: str = Field(min_length=10, max_length=4000)
    introspective_path: str = Field(min_length=20, max_length=4000)


class UniversalGenomeChangeInput(GenomeEvolutionInput):
    change_key: str = Field(min_length=1, max_length=120)


@router.get("/agent-genomes")
def read_agent_genomes():
    return {"genomes": list_agent_genomes()}


@router.get("/agent-authorities/{authority_id}/genome")
def read_agent_genome(authority_id: str):
    genome = get_agent_genome(authority_id)
    if genome is None:
        raise HTTPException(status_code=404, detail="Authority genome not found.")
    return genome


@router.post("/agent-authorities/{authority_id}/genome/evolve")
def evolve_authority_genome(authority_id: str, payload: GenomeEvolutionInput):
    try:
        genome = evolve_agent_genome(authority_id, **payload.model_dump())
    except ValueError as exc:
        if str(exc) == "agent authority not found":
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if "requires a tested, reviewed authority" in str(exc):
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"genome": genome}


@router.post("/agent-genomes/universal-changes")
def apply_universal_change(payload: UniversalGenomeChangeInput):
    try:
        result = apply_universal_genome_change(**payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return result
