import os
import sys

def main():
    print("Initializing AI Pool Coordinator repository structure...")
    
    # 1. Define folder structure
    directories = [
        "config",
        "src",
        "tests",
        ".github/workflows"
    ]
    for d in directories:
        os.makedirs(d, exist_ok=True)
        print(f"Created directory: {d}")

    # 2. Define files and contents
    files = {}

    files["config/nodes.yaml"] = """nodes:
  - name: worker-primary
    url: http://worker-primary:11434
    models:
      - llama3
      - gemma
      - deepseek-r1
  - name: worker-secondary
    url: http://192.168.1.50:11434
    models:
      - llama3
      - codestral
"""

    files["pyproject.toml"] = """[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "ai-pool-coordinator"
version = "0.1.0"
description = "Custom distributed AI model pool and load balancer"
dependencies = [
    "fastapi>=0.110.0",
    "uvicorn>=0.28.0",
    "httpx>=0.27.0",
    "pydantic>=2.6.0",
    "pyyaml>=6.0.1"
]

[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
"""

    files["Dockerfile"] = """FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY . .

EXPOSE 8000

CMD ["uvicorn", "src.coordinator:app", "--host", "0.0.0.0", "--port", "8000"]
"""

    files["docker-compose.yml"] = """version: '3.8'

services:
  coordinator:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./config:/app/config
    environment:
      - PORT=8000

  worker-primary:
    image: ollama/ollama:latest
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama

volumes:
  ollama_data:
"""

    files["src/__init__.py"] = ""

    files["src/coordinator.py"] = """import yaml
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
"""

    files["src/health.py"] = """import yaml
import httpx
import asyncio
from pathlib import Path

CONFIG_PATH = Path("config/nodes.yaml")

async def check_node_health(node):
    url = f"{node['url']}/api/tags"
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            res = await client.get(url)
            if res.status_code == 200:
                print(f"[HEALTH] Node {node['name']} is ONLINE.")
                return True
        except Exception:
            pass
    print(f"[HEALTH] Node {node['name']} is OFFLINE.")
    return False

async def monitor_loop():
    while True:
        if CONFIG_PATH.exists():
            with open(CONFIG_PATH, "r") as f:
                data = yaml.safe_load(f)
            nodes = data.get("nodes", [])
            for node in nodes:
                await check_node_health(node)
        await asyncio.sleep(30)

if __name__ == "__main__":
    asyncio.run(monitor_loop())
"""

    files["src/proxy.py"] = """def translate_openai_to_ollama(openai_payload):
    messages = openai_payload.get("messages", [])
    prompt = ""
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        prompt += f"{role.upper()}: {content}\\n"
    
    return {
        "model": openai_payload.get("model", "llama3"),
        "prompt": prompt,
        "stream": openai_payload.get("stream", False)
    }

def translate_ollama_to_openai(ollama_response):
    return {
        "id": "chatcmpl-custom",
        "object": "chat.completion",
        "created": 1700000000,
        "model": ollama_response.get("model", "llama3"),
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": ollama_response.get("response", "")
            },
            "finish_reason": "stop"
        }]
    }
"""

    files["tests/test_router.py"] = """import pytest
from src.proxy import translate_openai_to_ollama, translate_ollama_to_openai

def test_translation_openai_to_ollama():
    openai_payload = {
        "model": "gemma",
        "messages": [
            {"role": "user", "content": "Hello!"}
        ],
        "stream": False
    }
    ollama_payload = translate_openai_to_ollama(openai_payload)
    assert ollama_payload["model"] == "gemma"
    assert "USER: Hello!" in ollama_payload["prompt"]
    assert ollama_payload["stream"] is False

def test_translation_ollama_to_openai():
    ollama_res = {
        "model": "gemma",
        "response": "Hello back!"
    }
    openai_res = translate_ollama_to_openai(ollama_res)
    assert openai_res["model"] == "gemma"
    assert openai_res["choices"][0]["message"]["content"] == "Hello back!"
"""

    files[".github/workflows/test.yml"] = """name: Python CI

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v3
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.12'
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install pytest fastapi httpx pyyaml pydantic uvicorn
    - name: Run tests
      run: |
        pytest
"""

    files["README.md"] = """# AI Pool Coordinator

A lightweight, modular, and containerized AI worker pool gateway and load balancer.

## Architecture

This coordinator intercepts requests aimed at standard LLM APIs, health-checks a registry of local or remote workers (e.g., local machines running Ollama), and routes request traffic across them in a round-robin cycle.

## Directory Layout
- `config/nodes.yaml`: Registry listing backend node URLs and their available model weights.
- `src/coordinator.py`: FastAPI-based API routing hub supporting streaming and static request proxies.
- `src/health.py`: Node status tracker pinging active worker endpoints.
- `src/proxy.py`: Translation module for bridging API formats.
- `tests/`: Basic routing and schema unit tests
"""

    for path, content in files.items():
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Created file: {path}")

    print("Repository initialization complete.")

if __name__ == "__main__":
    main()
