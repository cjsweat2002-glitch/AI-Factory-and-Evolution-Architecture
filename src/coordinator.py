import itertools
import json
import os
import secrets
import subprocess
from datetime import datetime
from pathlib import Path

import httpx
import yaml
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from typing import Literal
from src.autonomy_store import delete_push_subscription
from src.autonomy_graph_api import router as autonomy_graph_router
from src.genome_api import router as genome_router

from src.autonomy_store import (
    agent_net_deviation,
    attach_authority_worktree,
    create_outcome,
    create_agent_issue_draft,
    create_agent_cycle,
    evaluate_agent_authority,
    expand_agent_authorities,
    get_agent_authority,
    get_agent_cycle,
    get_shared_learning_opt_in,
    list_agent_issue_drafts,
    list_outcomes,
    save_push_subscription,
    set_shared_learning_opt_in,
    verify_outcome,
    verified_outcome_summary,
)
from src.authority_worktrees import apply_authority_patch, create_authority_worktree
from src.factory import start_background_curiosity
from src.factory_memory import log_repo_memory
from src.factory_worker import list_background_jobs, run_background_job
from src.notebook_guard import safe_import_notebook
from src.native_agents import (
    parse_expansion_response,
    parse_issue_draft_response,
    run_native_agent,
)
from src.research_api import router as research_router
from src.push_notifications import public_vapid_key, send_push_notification
from src.web_inspiration import ingest_web_inspiration

app = FastAPI(title="AI Pool Gateway")
app.include_router(research_router)
app.include_router(autonomy_graph_router)
app.include_router(genome_router)

CONFIG_PATH = Path("config/nodes.yaml")
PUBLIC_PATHS = {"/", "/dashboard", "/manifest.webmanifest", "/service-worker.js", "/auth/config", "/healthz"}


class OutcomeInput(BaseModel):
    agent_id: str = Field(min_length=1, max_length=100)
    contributor_id: str = Field(min_length=1, max_length=100)
    metric: Literal[
        "quality",
        "adoption",
        "reusable_contribution",
        "time_saved",
        "cost_saved",
        "maintenance_cost",
        "negative_impact",
    ]
    baseline: float = Field(allow_inf_nan=False)
    observed: float = Field(allow_inf_nan=False)
    unit: str = Field(min_length=1, max_length=40)
    evidence: str = Field(min_length=10, max_length=2000)


class OutcomeReview(BaseModel):
    review_note: str = Field(min_length=10, max_length=1000)


class SharedLearningPreference(BaseModel):
    opted_in: bool


class PushSubscriptionInput(BaseModel):
    subscription: dict


class PushSubscriptionDelete(BaseModel):
    endpoint: str


class AgentCycleInput(BaseModel):
    objective: str = Field(min_length=10, max_length=2000)
    base_branch: str = Field(min_length=1, max_length=255)
    resource_budget: float = Field(gt=0, allow_inf_nan=False)
    source_issue: str | None = Field(default=None, max_length=255)


class AgentIssueGenerationInput(BaseModel):
    focus: str = Field(
        default="Find the highest-value evidence-backed improvement in this repository.",
        max_length=1000,
    )


class AgentAuthorityEvaluation(BaseModel):
    tests_passed: bool
    reviewer_approved: bool
    evidence: str = Field(min_length=10, max_length=4000)
    actual_gain: float = Field(allow_inf_nan=False)


@app.middleware("http")
async def require_owner_access(request: Request, call_next):
    if request.url.path in PUBLIC_PATHS:
        return await call_next(request)
    expected_token = os.getenv("AI_FACTORY_ACCESS_TOKEN", "")
    if len(expected_token) < 32:
        return JSONResponse(
            {"detail": "Owner access is not configured. Set AI_FACTORY_ACCESS_TOKEN to a random secret of at least 32 characters."},
            status_code=503,
        )
    authorization = request.headers.get("authorization", "")
    scheme, _, supplied_token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not secrets.compare_digest(
        supplied_token, expected_token
    ):
        return JSONResponse({"detail": "Owner authentication required."}, status_code=401)
    return await call_next(request)


def load_nodes():
    env_nodes = os.getenv("AI_FACTORY_NODES")
    if env_nodes:
        try:
            parsed = json.loads(env_nodes)
            if isinstance(parsed, list) and parsed:
                return parsed
        except json.JSONDecodeError:
            pass

    env_worker_url = os.getenv("AI_FACTORY_WORKER_URL")
    if env_worker_url:
        return [{"name": "env-worker", "url": env_worker_url, "models": [os.getenv("AI_FACTORY_MODEL", "llama3")]}]

    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r") as f:
            data = yaml.safe_load(f) or {}
            return data.get("nodes", [])
    return [{"name": "default", "url": "http://localhost:11434", "models": ["llama3"]}]


_node_iterator = None
_node_signature = None


def get_next_node():
    global _node_iterator, _node_signature
    nodes = load_nodes()
    if not nodes:
        raise HTTPException(status_code=503, detail="No worker nodes registered.")

    signature = tuple(
        (node.get("name"), node.get("url"), tuple(node.get("models", [])))
        for node in nodes
    )
    if _node_iterator is None or signature != _node_signature:
        _node_iterator = itertools.cycle(nodes)
        _node_signature = signature
    return next(_node_iterator)


def build_worker_headers(target_url: str):
    headers = {}
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_API_TOKEN")
    if api_key and ("api.openai.com" in target_url or "openai.com" in target_url):
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


@app.get("/", response_class=HTMLResponse)
async def root_page():
    return FileResponse("templates/dashboard.html")


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page():
    return FileResponse("templates/dashboard.html")


@app.get("/auth/config")
async def auth_config():
    return {"access_token_configured": len(os.getenv("AI_FACTORY_ACCESS_TOKEN", "")) >= 32}


@app.get("/healthz")
async def health_check():
    return {"status": "ok"}


@app.get("/manifest.webmanifest")
async def pwa_manifest():
    return FileResponse("templates/manifest.webmanifest", media_type="application/manifest+json")


@app.get("/service-worker.js")
async def service_worker():
    return FileResponse("templates/service-worker.js", media_type="application/javascript")


@app.get("/notifications/config")
async def notification_config():
    key = public_vapid_key()
    if not key:
        raise HTTPException(
            status_code=503,
            detail="Phone notifications are not configured. Set VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY, and VAPID_CLAIMS_EMAIL.",
        )
    return {"public_key": key}


@app.post("/notifications/subscribe")
async def subscribe_to_notifications(payload: PushSubscriptionInput):
    try:
        save_push_subscription(payload.subscription)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "subscribed"}


@app.delete("/notifications/subscribe")
async def unsubscribe_from_notifications(payload: PushSubscriptionDelete):
    delete_push_subscription(payload.endpoint)
    return {"status": "unsubscribed"}


@app.get("/autonomy/outcomes")
async def autonomy_outcomes(agent_id: str | None = None):
    return {"outcomes": list_outcomes(agent_id)}


@app.post("/autonomy/outcomes")
async def submit_autonomy_outcome(payload: OutcomeInput):
    try:
        outcome = create_outcome(**payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"status": "pending_review", "outcome": outcome}


@app.post("/autonomy/outcomes/{outcome_id}/verify")
async def review_autonomy_outcome(outcome_id: str, payload: OutcomeReview):
    outcome = verify_outcome(outcome_id, payload.review_note)
    if outcome is None:
        raise HTTPException(status_code=404, detail="Pending outcome not found.")
    send_push_notification(
        "Agent outcome reviewed",
        "A measured agent outcome is ready for its next private learning cycle.",
        "outcome-verified",
    )
    return {"status": "verified", "outcome": outcome}


@app.get("/autonomy/agents/{agent_id}/net-deviation")
async def autonomy_net_deviation(agent_id: str):
    return agent_net_deviation(agent_id)


@app.get("/autonomy/shared-learning")
async def shared_learning_preference():
    return {
        "opted_in": get_shared_learning_opt_in(),
        "shared_aggregation_active": False,
        "notice": "Shared aggregation is not active in this single-user release; no outcome data is sent to other users.",
    }


@app.put("/autonomy/shared-learning")
async def update_shared_learning_preference(payload: SharedLearningPreference):
    set_shared_learning_opt_in(payload.opted_in)
    return await shared_learning_preference()


def _agent_repository_context(repository: Path | None = None) -> str:
    repository = (
        repository.resolve()
        if repository is not None
        else Path(os.getenv("AI_FACTORY_REPOSITORY_PATH", ".")).resolve()
    )
    context_parts = []
    budget = 40000
    for relative_path in (
        "README.md",
        "src/coordinator.py",
        "src/autonomy_store.py",
        "src/factory.py",
        "src/factory_worker.py",
    ):
        file_path = repository / relative_path
        if not file_path.is_file():
            continue
        try:
            content = file_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise HTTPException(
                status_code=503,
                detail=f"Could not read repository context file {relative_path}: {exc}",
            ) from exc
        remaining = budget - sum(len(part) for part in context_parts)
        if remaining <= 0:
            break
        context_parts.append(f"--- {relative_path} ---\n{content[:remaining]}")
    if not context_parts:
        raise HTTPException(
            status_code=503,
            detail="No readable repository context files were found.",
        )
    return "\n\n".join(context_parts)


@app.get("/autonomy/agent-issues")
def read_agent_issue_drafts():
    return {"issues": list_agent_issue_drafts()}


@app.post("/autonomy/agent-issues/generate")
def generate_agent_issue_draft(payload: AgentIssueGenerationInput):
    context = _agent_repository_context()
    try:
        response = run_native_agent(
            "scout",
            payload.focus,
            branch_ref="main",
            context=context,
        )
        issue = parse_issue_draft_response(response)
        saved_issue = create_agent_issue_draft(**issue)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Native scout could not produce a valid issue draft: {exc}",
        ) from exc
    return {"issue": saved_issue}


@app.post("/autonomy/agent-cycles")
def start_agent_cycle(payload: AgentCycleInput):
    try:
        return create_agent_cycle(**payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/autonomy/agent-cycles/{cycle_id}")
def read_agent_cycle(cycle_id: str):
    cycle = get_agent_cycle(cycle_id)
    if cycle is None:
        raise HTTPException(status_code=404, detail="Agent cycle not found.")
    return cycle


@app.post("/autonomy/agent-cycles/{cycle_id}/authorities/{authority_id}/expand")
def expand_agent_authority(cycle_id: str, authority_id: str):
    cycle = get_agent_cycle(cycle_id)
    if cycle is None:
        raise HTTPException(status_code=404, detail="Agent cycle not found.")
    parent = next(
        (authority for authority in cycle["authorities"] if authority["id"] == authority_id),
        None,
    )
    if parent is None:
        raise HTTPException(status_code=404, detail="Authority not found in this cycle.")
    if parent["status"] != "active" or cycle["cycle"]["status"] != "exploring":
        raise HTTPException(status_code=409, detail="Only active authorities can expand.")

    parent_worktree = parent.get("worktree_path")
    if parent["parent_id"] is not None:
        if not parent_worktree or not Path(parent_worktree).is_dir():
            raise HTTPException(
                status_code=409,
                detail="Create the parent authority's workspace before expanding it.",
            )
        repository_context = Path(parent_worktree)
    else:
        repository_context = None

    try:
        context = _agent_repository_context(repository_context)
        response = run_native_agent(
            "planner",
            parent["objective"],
            branch_ref=parent["branch_ref"],
            authority_id=parent["id"],
            evidence=parent.get("proposal_evidence") or "",
            context=context,
        )
        proposals = parse_expansion_response(response)
        authorities = expand_agent_authorities(cycle_id, authority_id, proposals)
    except (OSError, RuntimeError, ValueError) as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Native planner could not produce valid authority proposals: {exc}",
        ) from exc
    return {"authorities": authorities, "count": len(authorities)}


@app.post("/autonomy/agent-authorities/{authority_id}/workspace")
def create_agent_authority_workspace(authority_id: str):
    authority = get_agent_authority(authority_id)
    if authority is None:
        raise HTTPException(status_code=404, detail="Authority not found.")
    if authority["status"] != "active":
        raise HTTPException(status_code=409, detail="Only active authorities can get a workspace.")
    if authority["worktree_path"]:
        worktree_path = Path(authority["worktree_path"])
        if worktree_path.is_dir():
            return {"authority": authority, "worktree_path": str(worktree_path)}
        raise HTTPException(
            status_code=409,
            detail="Authority worktree is recorded but missing from disk; manual recovery is required.",
        )

    cycle = get_agent_cycle(authority["cycle_id"])
    if cycle is None:
        raise HTTPException(status_code=404, detail="Agent cycle not found.")
    parent = next(
        (
            candidate
            for candidate in cycle["authorities"]
            if candidate["id"] == authority["parent_id"]
        ),
        None,
    )
    if parent is None:
        raise HTTPException(status_code=409, detail="Authority parent is unavailable.")
    if parent["parent_id"] is not None and not parent["worktree_path"]:
        raise HTTPException(
            status_code=409,
            detail="Create the parent authority's workspace before this child workspace.",
        )
    if parent["parent_id"] is not None and not Path(parent["worktree_path"]).is_dir():
        raise HTTPException(
            status_code=409,
            detail="Parent authority worktree is missing from disk.",
        )

    repository = Path(os.getenv("AI_FACTORY_REPOSITORY_PATH", ".")).resolve()
    configured_root = os.getenv("AI_FACTORY_WORKTREE_DIR")
    worktree_root = (
        Path(configured_root).resolve()
        if configured_root
        else repository.parent / f"{repository.name}-authorities"
    )
    try:
        workspace = create_authority_worktree(
            repository=repository,
            worktree_root=worktree_root,
            cycle_id=authority["cycle_id"],
            authority_id=authority["id"],
            base_branch=parent["branch_ref"],
        )
        if workspace["branch_ref"] != authority["branch_ref"]:
            raise RuntimeError("created branch does not match the recorded authority ref")
        saved_authority = attach_authority_worktree(
            authority_id, workspace["worktree_path"]
        )
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (OSError, RuntimeError, subprocess.CalledProcessError, ValueError) as exc:
        raise HTTPException(
            status_code=409,
            detail=f"Could not create an isolated authority worktree: {exc}",
        ) from exc
    return {"authority": saved_authority, **workspace}


@app.post("/autonomy/agent-authorities/{authority_id}/implement")
def implement_agent_authority(authority_id: str):
    authority = get_agent_authority(authority_id)
    if authority is None:
        raise HTTPException(status_code=404, detail="Authority not found.")
    if authority["status"] != "active":
        raise HTTPException(status_code=409, detail="Only active authorities can be implemented.")
    if authority["role"] != "builder":
        raise HTTPException(
            status_code=409,
            detail="Only builder authorities can request a branch-scoped implementation.",
        )
    worktree_path = authority["worktree_path"]
    if not worktree_path or not Path(worktree_path).is_dir():
        raise HTTPException(
            status_code=409,
            detail="Create the authority's worktree before requesting implementation.",
        )

    try:
        context = _agent_repository_context(Path(worktree_path))
        patch = run_native_agent(
            "builder",
            authority["objective"],
            branch_ref=authority["branch_ref"],
            authority_id=authority["id"],
            evidence=authority["proposal_evidence"] or "",
            context=context,
        )
        diff_stat = apply_authority_patch(
            worktree_path,
            patch,
            expected_branch=authority["branch_ref"],
        )
    except HTTPException:
        raise
    except (OSError, RuntimeError, subprocess.CalledProcessError, ValueError) as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Authority implementation was not applied: {exc}",
        ) from exc
    return {
        "authority_id": authority_id,
        "branch_ref": authority["branch_ref"],
        "diff_stat": diff_stat,
        "tests_executed": False,
        "status": "implementation_ready_for_validation",
    }


@app.post("/autonomy/agent-authorities/{authority_id}/evaluate")
def evaluate_agent_authority_route(
    authority_id: str, payload: AgentAuthorityEvaluation
):
    try:
        authority = evaluate_agent_authority(
            authority_id, **payload.model_dump()
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if authority is None:
        raise HTTPException(status_code=404, detail="Authority not found.")
    return {"authority": authority}


@app.post("/api/chat")
async def chat_from_dashboard(request: Request):
    payload = await request.json()
    message = payload.get("message", "").strip()
    model = payload.get("model", "llama3")
    if not message:
        return JSONResponse({"error": "No message provided."}, status_code=400)

    upstream_payload = {
        "model": model,
        "messages": [{"role": "user", "content": message}],
        "stream": False,
    }
    target_node = get_next_node()
    target_url = f"{target_node['url']}/v1/chat/completions"

    try:
        headers = build_worker_headers(target_url)
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(target_url, json=upstream_payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            return {"reply": content, "model": model}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI worker unavailable: {str(exc)}")


@app.post("/api/frontend/chat")
async def frontend_chat_bridge(request: Request):
    payload = await request.json()
    messages = payload.get("messages") or [{"role": "user", "content": payload.get("message", "")}]
    model = payload.get("model", "llama3")
    stream = payload.get("stream", False)
    if not messages:
        return JSONResponse({"error": "No message provided."}, status_code=400)

    target_node = get_next_node()
    target_url = f"{target_node['url']}/v1/chat/completions"

    try:
        headers = build_worker_headers(target_url)
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                target_url,
                json={"model": model, "messages": messages, "stream": stream},
                headers=headers,
            )
            response.raise_for_status()

            if stream:
                async def stream_generator():
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            data_str = line[6:]
                            if data_str.strip() == "[DONE]":
                                break
                            try:
                                chunk_data = json.loads(data_str)
                                delta = chunk_data.get("choices", [{}])[0].get("delta", {})
                                if "content" in delta:
                                    chunk = {"choices": [{"delta": {"content": delta["content"]}}]}
                                    yield f"data: {json.dumps(chunk)}\n\n"
                            except json.JSONDecodeError:
                                pass
                    yield "data: [DONE]\n\n"

                return StreamingResponse(stream_generator(), media_type="text/event-stream")
            else:
                data = response.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content") if data.get("choices") else data.get("response", "")
                return {
                    "id": "chatcmpl-frontend",
                    "object": "chat.completion",
                    "created": int(datetime.now().timestamp()),
                    "model": data.get("model", model),
                    "choices": [{
                        "index": 0,
                        "message": {"role": "assistant", "content": content},
                        "finish_reason": "stop",
                    }],
                }
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Frontend AI bridge failed: {str(exc)}")


@app.post("/api/notebooks/import")
async def import_notebook(request: Request):
    try:
        form = await request.form()
        uploaded_file = form.get("file") if form else None
        if uploaded_file is not None:
            notebook_path = Path("uploads") / (uploaded_file.filename or "notebook.ipynb")
            notebook_path.parent.mkdir(parents=True, exist_ok=True)
            notebook_path.write_bytes(await uploaded_file.read())
            data = safe_import_notebook(notebook_path)
            return {"status": "imported", "notebook": str(notebook_path), "safe": True, "cells": data["cells"]}

        body = await request.json()
        if "notebook_path" in body:
            data = safe_import_notebook(Path(body["notebook_path"]))
            return {"status": "imported", "notebook": body["notebook_path"], "safe": True, "cells": data["cells"]}

        if "notebook_content" in body:
            notebook_path = Path("uploads") / "imported_notebook.ipynb"
            notebook_path.parent.mkdir(parents=True, exist_ok=True)
            notebook_path.write_text(body["notebook_content"], encoding="utf-8")
            data = safe_import_notebook(notebook_path)
            return {"status": "imported", "notebook": str(notebook_path), "safe": True, "cells": data["cells"]}

        return JSONResponse({"error": "No notebook content or path supplied."}, status_code=400)
    except Exception as exc:
        return JSONResponse({"error": f"Notebook import failed: {str(exc)}"}, status_code=400)


@app.post("/factory/curiosity")
async def create_curiosity(request: Request):
    payload = await request.json()
    topic = payload.get("topic", "general repo improvement")
    model = payload.get("model", "llama3")
    agent_id = payload.get("agent_id", "personal-agent")
    learning_context = verified_outcome_summary(agent_id)
    root = Path("background")
    root.mkdir(parents=True, exist_ok=True)
    folder = root / f"curiosity_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
    session = start_background_curiosity(
        str(folder), topic, model=model, learning_context=learning_context
    )
    job = run_background_job(str(folder), topic, model=model)
    return {"status": "queued", "session": session, "job": job}


@app.post("/factory/memory")
async def add_factory_memory(request: Request):
    payload = await request.json()
    title = payload.get("title", "Factory update")
    summary = payload.get("summary", "Repository evolved through the factory loop.")
    memory_root = Path("memory")
    memory_root.mkdir(parents=True, exist_ok=True)
    result = log_repo_memory(str(memory_root), title, summary)
    return {"status": "updated", "memory": result}


@app.post("/factory/inspiration")
async def add_factory_inspiration(request: Request):
    payload = await request.json()
    topic = payload.get("topic", "general AI learning")
    sources = payload.get("sources", [])
    memory_root = Path("memory")
    memory_root.mkdir(parents=True, exist_ok=True)
    entries = ingest_web_inspiration(str(memory_root), topic, sources=sources)
    return {"status": "ingested", "entries": entries}


@app.get("/factory/status")
async def factory_status():
    # Collect jobs from all curiosity session folders
    background_root = Path("background")
    all_jobs = []
    
    if background_root.exists():
        for session_folder in background_root.iterdir():
            if session_folder.is_dir():
                jobs = list_background_jobs(str(session_folder))
                all_jobs.extend(jobs)
    
    # Also check the root background folder for any direct jobs
    root_jobs = list_background_jobs("background")
    all_jobs.extend(root_jobs)
    
    memory_dir = Path("memory")
    return {
        "status": "running",
        "background_jobs": all_jobs,
        "memory_dir": str(memory_dir),
        "has_memory": memory_dir.exists(),
    }


@app.api_route("/v1/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_request(path: str, request: Request):
    target_node = get_next_node()
    target_url = f"{target_node['url']}/v1/{path}"

    client_body = await request.body()
    headers = dict(request.headers)
    headers.pop("host", None)
    openai_headers = build_worker_headers(target_url)
    headers.update(openai_headers)

    async def stream_generator(response):
        async for chunk in response.aiter_bytes():
            yield chunk

    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            is_stream = False
            if request.method == "POST":
                try:
                    body_json = await request.json()
                    is_stream = body_json.get("stream", False)
                except Exception:
                    pass

            if is_stream:
                req = client.build_request(
                    method=request.method,
                    url=target_url,
                    content=client_body,
                    headers=headers,
                )
                response = await client.send(req, stream=True)
                return StreamingResponse(
                    stream_generator(response),
                    status_code=response.status_code,
                    headers=dict(response.headers),
                )
            else:
                response = await client.request(
                    method=request.method,
                    url=target_url,
                    content=client_body,
                    headers=headers,
                )
                return response.json()
        except httpx.RequestError as e:
            raise HTTPException(status_code=503, detail=f"Worker node '{target_node['name']}' offline: {str(e)}")
