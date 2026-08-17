import itertools
from datetime import datetime
from pathlib import Path

import httpx
import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse

from src.factory import start_background_curiosity
from src.factory_memory import log_repo_memory
from src.factory_worker import list_background_jobs, run_background_job
from src.web_inspiration import ingest_web_inspiration

app = FastAPI(title="AI Pool Gateway")

CONFIG_PATH = Path("config/nodes.yaml")


def load_nodes():
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r") as f:
            data = yaml.safe_load(f) or {}
            return data.get("nodes", [])
    return [{"name": "default", "url": "http://localhost:11434", "models": ["llama3"]}]


_node_iterator = None


def get_next_node():
    global _node_iterator
    nodes = load_nodes()
    if not nodes:
        raise HTTPException(status_code=503, detail="No worker nodes registered.")
    if _node_iterator is None:
        _node_iterator = itertools.cycle(nodes)
    return next(_node_iterator)


@app.get("/", response_class=HTMLResponse)
async def root_page():
    nodes = load_nodes()
    nodes_html = "\n".join(
        f"<li><strong>{node.get('name', 'worker')}</strong> — {node.get('url', 'unknown')}<br><small>Models: {', '.join(node.get('models', [])) or 'n/a'}</small></li>"
        for node in nodes
    )
    if not nodes_html:
        nodes_html = "<li>No workers registered.</li>"

    return f"""
    <html>
      <head>
        <title>AI Pool Coordinator</title>
        <style>
          body {{ font-family: Arial, sans-serif; margin: 2rem; background: #0f172a; color: #e2e8f0; }}
          .card {{ max-width: 900px; margin: auto; background: #111827; padding: 2rem; border-radius: 12px; }}
          h1 {{ color: #7dd3fc; }}
          ul {{ line-height: 1.8; }}
          code {{ background: #1f2937; padding: 0.2rem 0.4rem; border-radius: 6px; }}
        </style>
      </head>
      <body>
        <div class="card">
          <h1>AI Pool Coordinator</h1>
          <p>OpenAI-compatible request gateway with round-robin worker routing and health-aware selection.</p>
          <p><strong>Worker Pool</strong></p>
          <ul>{nodes_html}</ul>
          <p><strong>Factory AI Layers</strong></p>
          <ul>
            <li>Curiosity jobs: <code>/factory/curiosity</code></li>
            <li>Repo memory: <code>/factory/memory</code></li>
            <li>Web inspiration ingestion: <code>/factory/inspiration</code></li>
            <li>Status: <code>/factory/status</code></li>
          </ul>
          <p>Endpoints: <code>/v1/chat/completions</code>, <code>/v1/models</code>, and more.</p>
        </div>
      </body>
    </html>
    """


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


@app.api_route("/v1/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_request(path: str, request: Request):
    target_node = get_next_node()
    target_url = f"{target_node['url']}/v1/{path}"

    client_body = await request.body()
    headers = dict(request.headers)
    headers.pop("host", None)

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
