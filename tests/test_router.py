import pytest
from fastapi.testclient import TestClient
from src.coordinator import app
from src.factory import generate_curiosity_prompt, start_background_curiosity
from src.factory_worker import run_background_job, list_background_jobs
from src.factory_memory import log_repo_memory
from src.web_inspiration import ingest_web_inspiration
from src.proxy import translate_openai_to_ollama, translate_ollama_to_openai

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
    assert "AI Pool Coordinator" in response.text
    assert "Worker Pool" in response.text


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
