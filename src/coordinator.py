import itertools
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path

import httpx
import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse

from src.factory import start_background_curiosity
from src.factory_memory import log_repo_memory
from src.factory_worker import list_background_jobs, run_background_job
from src.notebook_guard import safe_import_notebook
from src.web_inspiration import ingest_web_inspiration

app = FastAPI(title="AI Pool Gateway")

CONFIG_PATH = Path("config/nodes.yaml")


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
    root = Path("background")
    root.mkdir(parents=True, exist_ok=True)
    folder = root / f"curiosity_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
    session = start_background_curiosity(str(folder), topic, model=model)
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
    background_jobs = list_background_jobs("background")
    memory_dir = Path("memory")
    return {
        "status": "running",
        "background_jobs": background_jobs,
        "memory_dir": str(memory_dir),
        "has_memory": memory_dir.exists(),
    }


@app.post("/factory/github/push")
async def push_factory_changes(request: Request):
    payload = await request.json()
    message = payload.get("message", "Factory update from the AI dashboard")
    repo = payload.get("repo") or os.getenv("GITHUB_REPO")
    branch = payload.get("branch") or os.getenv("GITHUB_BRANCH", "main")
    token = payload.get("token") or os.getenv("GITHUB_TOKEN")

    if not repo:
        return JSONResponse({"error": "GitHub repo is not configured. Set GITHUB_REPO."}, status_code=400)
    if not token:
        return JSONResponse({"error": "GitHub token is not configured. Set GITHUB_TOKEN."}, status_code=400)

    repo_path = Path(".").resolve()
    remote_url = f"https://x-access-token:{token}@github.com/{repo}.git"

    try:
        subprocess.run(["git", "config", "user.name", "AI Factory Bot"], cwd=str(repo_path), check=True, capture_output=True, text=True)
        subprocess.run(["git", "config", "user.email", "factory-bot@example.com"], cwd=str(repo_path), check=True, capture_output=True, text=True)
        subprocess.run(["git", "add", "-A"], cwd=str(repo_path), check=True, capture_output=True, text=True)
        subprocess.run(["git", "commit", "-m", message], cwd=str(repo_path), check=True, capture_output=True, text=True)
        subprocess.run(["git", "remote", "set-url", "origin", remote_url], cwd=str(repo_path), check=True, capture_output=True, text=True)
        subprocess.run(["git", "push", "origin", branch], cwd=str(repo_path), check=True, capture_output=True, text=True)
        return {"status": "pushed", "repo": repo, "branch": branch, "message": message}
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        stdout = (exc.stdout or "").strip()
        return JSONResponse({
            "status": "push_failed",
            "repo": repo,
            "branch": branch,
            "stderr": stderr or stdout or str(exc),
        }, status_code=500)


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
