import json

import pytest
from fastapi.testclient import TestClient

from src.coordinator import app
from src.factory import generate_curiosity_prompt, start_background_curiosity
from src.factory_memory import log_repo_memory
from src.factory_worker import list_background_jobs, run_background_job
from src.notebook_guard import safe_import_notebook
from src.proxy import translate_openai_to_ollama, translate_ollama_to_openai
from src.web_inspiration import ingest_web_inspiration

client = TestClient(app)

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


def test_root_page_renders_dashboard():
    response = client.get("/")
    assert response.status_code == 200
    assert "AI Factory Dashboard" in response.text
    assert "Worker pool" in response.text


def test_generate_curiosity_prompt_contains_workspace_guidance():
    prompt = generate_curiosity_prompt("web research", "/tmp/factory-demo")
    assert "web research" in prompt
    assert "/tmp/factory-demo" in prompt
    assert "curiosity" in prompt.lower()


def test_start_background_curiosity_creates_record(tmp_path):
    session = start_background_curiosity(str(tmp_path), "prototype better routing", model="llama3")
    assert session["folder"] == str(tmp_path)
    assert session["model"] == "llama3"
    assert session["status"] in {"queued", "running"}
    assert "job_id" in session


def test_background_job_runs_and_tracks_status(tmp_path):
    job = run_background_job(str(tmp_path), "research new pattern", model="llama3")
    assert job["status"] == "completed"
    assert job["job_id"]
    jobs = list_background_jobs(str(tmp_path))
    assert any(item["job_id"] == job["job_id"] for item in jobs)


def test_repo_memory_is_logged(tmp_path):
    summary = log_repo_memory(str(tmp_path), "Add a learning loop", "The factory now records repository improvements.")
    assert summary["title"] == "Add a learning loop"
    assert (tmp_path / "repo_memory" / "decisions.md").exists()


def test_web_inspiration_ingestion_creates_sources(tmp_path):
    entries = ingest_web_inspiration(str(tmp_path), "prompt engineering", sources=["https://example.com/ai-patterns"])
    assert entries
    assert any(item["source"].startswith("https://") for item in entries)


def test_factory_api_layers_update_repo_state():
    curiosity = client.post("/factory/curiosity", json={"topic": "better routing", "model": "llama3"})
    assert curiosity.status_code == 200
    assert curiosity.json()["status"] == "queued"

    memory = client.post("/factory/memory", json={"title": "Factory update", "summary": "The AI factory stored a new memory."})
    assert memory.status_code == 200
    assert memory.json()["status"] == "updated"

    inspiration = client.post("/factory/inspiration", json={"topic": "learning loops", "sources": ["https://example.com/factory"]})
    assert inspiration.status_code == 200
    assert inspiration.json()["status"] == "ingested"


def test_safe_import_notebook_extracts_cells(tmp_path):
    notebook_path = tmp_path / "safe_demo.ipynb"
    payload = {
        "cells": [
            {"cell_type": "markdown", "source": ["# Demo"]},
            {"cell_type": "code", "source": ["print('hello')\n"]},
        ],
        "metadata": {"kernelspec": {"name": "python3"}, "nbformat": 4},
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    notebook_path.write_text(json.dumps(payload), encoding="utf-8")

    data = safe_import_notebook(notebook_path)

    assert data["metadata"]["nbformat"] == 4
    assert len(data["cells"]) == 2
    assert data["cells"][1]["source"] == "print('hello')\n"


def test_frontend_chat_bridge_returns_worker_response(monkeypatch):
    class FakeResponse:
        def __init__(self):
            self.status_code = 200
            self._payload = {"model": "gemma", "response": "Connected successfully"}
            self.headers = {}

        def json(self):
            return self._payload

        def raise_for_status(self):
            return None

    async def fake_post(self, *args, **kwargs):
        return FakeResponse()

    monkeypatch.setattr("httpx.AsyncClient.post", fake_post)

    response = client.post(
        "/api/frontend/chat",
        json={
            "model": "gemma",
            "messages": [{"role": "user", "content": "Test question"}],
            "stream": False,
        },
    )

    assert response.status_code == 200
    assert response.json()["model"] == "gemma"
    assert "Connected successfully" in response.json()["choices"][0]["message"]["content"]
