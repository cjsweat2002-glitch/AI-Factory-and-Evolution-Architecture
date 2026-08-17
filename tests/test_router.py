import pytest
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
