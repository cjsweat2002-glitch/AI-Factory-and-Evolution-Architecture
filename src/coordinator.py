import yaml
import httpx
import itertools
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse

app = FastAPI(title="AI Pool Gateway")

CONFIG_PATH = Path("config/nodes.yaml")

def load_nodes():
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r") as f:
            return yaml.safe_load(f).get("nodes", [])
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
                    headers=headers
                )
                response = await client.send(req, stream=True)
                return StreamingResponse(
                    stream_generator(response),
                    status_code=response.status_code,
                    headers=dict(response.headers)
                )
            else:
                response = await client.request(
                    method=request.method,
                    url=target_url,
                    content=client_body,
                    headers=headers
                )
                return response.json()
        except httpx.RequestError as e:
            raise HTTPException(status_code=503, detail=f"Worker node '{target_node['name']}' offline: {str(e)}")
