import os
import sys
from datetime import datetime
from pathlib import Path

import httpx

from src.factory import generate_curiosity_prompt, start_background_curiosity

DEFAULT_MODEL = os.getenv("AI_FACTORY_MODEL", "llama3")


def resolve_base_url() -> str:
    candidates = [
        os.getenv("AI_FACTORY_API_URL"),
        os.getenv("OPENAI_BASE_URL"),
        os.getenv("OLLAMA_BASE_URL"),
    ]
    for candidate in candidates:
        if candidate:
            return candidate.rstrip("/")
    return "http://localhost:8000"


def chat_with_model(prompt: str, model: str = DEFAULT_MODEL) -> str:
    base_url = resolve_base_url()
    api_url = base_url.rstrip("/") + "/v1/chat/completions"

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }

    headers = {"Content-Type": "application/json"}
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("AI_FACTORY_API_KEY")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    response = httpx.post(api_url, json=payload, headers=headers, timeout=120.0)
    if response.status_code != 200:
        raise RuntimeError(f"Chat request failed ({response.status_code}): {response.text}")

    data = response.json()
    return data["choices"][0]["message"]["content"]


def print_help() -> None:
    print("Available commands:")
    print("  !help              Show this help")
    print("  !curiosity <topic> Start a background curiosity task in a new folder")
    print("  !model <name>      Switch the model for this chat session")
    print("  exit / quit        Leave the terminal")


def main() -> None:
    model = DEFAULT_MODEL
    print("AI Factory terminal ready.")
    print(f"Using model: {model}")
    print_help()

    while True:
        try:
            user_input = input("factory> ")
        except EOFError:
            print()
            break

        text = user_input.strip()
        if not text:
            continue
        if text.lower() in {"exit", "quit"}:
            print("Goodbye.")
            break
        if text.lower() == "!help":
            print_help()
            continue
        if text.startswith("!model "):
            model = text.split(None, 1)[1].strip() or model
            print(f"Model switched to {model}")
            continue
        if text.startswith("!curiosity"):
            topic = text[len("!curiosity") :].strip() or "general repo improvement"
            folder = Path("background") / f"curiosity_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
            session = start_background_curiosity(str(folder), topic, model=model)
            print(f"Background curiosity started: {session['job_id']}")
            print(f"Folder: {session['folder']}")
            curiosity_prompt = generate_curiosity_prompt(topic, session["folder"])
            try:
                reply = chat_with_model(curiosity_prompt, model=model)
                print(reply)
            except Exception as exc:  # pragma: no cover - interactive terminal fallback
                print(f"Background job queued, but live reply failed: {exc}")
            continue

        try:
            answer = chat_with_model(text, model=model)
            print(answer)
        except Exception as exc:
            print(f"Chat failed: {exc}")


if __name__ == "__main__":
    main()
