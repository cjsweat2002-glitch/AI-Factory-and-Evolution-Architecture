import json

import pytest

from src.research_search import search_public_web


def test_search_returns_bounded_https_leads_and_sanitizes_snippets(
    monkeypatch,
):
    monkeypatch.setenv(
        "AI_FACTORY_RESEARCH_SEARCH_URL",
        "https://search.example.test/search",
    )
    response_payload = {
        "results": [
            {
                "title": "Validated result",
                "url": "https://example.test/article",
                "content": "<b>Useful</b>\n evidence",
                "engine": "test",
            },
            {
                "title": "Insecure result",
                "url": "http://example.test/article",
                "content": "must be omitted",
            },
            {
                "title": "Private IP result",
                "url": "https://127.0.0.1/private",
                "content": "must be omitted",
            },
            {
                "title": "Duplicate result",
                "url": "https://example.test/article",
                "content": "must be deduplicated",
            },
        ]
    }
    captured = []

    class FakeResponse:
        status_code = 200

        def iter_bytes(self):
            yield json.dumps(response_payload).encode("utf-8")

    class FakeClient:
        def __init__(self, **kwargs):
            captured.append(("client", kwargs))

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def stream(self, method, url, **kwargs):
            captured.append((method, url, kwargs))

            class ResponseContext:
                def __enter__(self):
                    return FakeResponse()

                def __exit__(self, *args):
                    return False

            return ResponseContext()

    monkeypatch.setattr("src.research_search.httpx.Client", FakeClient)
    leads = search_public_web("validated low-resource worker routing")

    assert len(leads) == 1
    assert leads[0]["snippet"] == "Useful evidence"
    assert captured[1][1] == "https://search.example.test/search"
    assert captured[1][2]["params"]["format"] == "json"


def test_search_provider_is_configured_by_environment_and_response_is_bounded(
    monkeypatch,
):
    monkeypatch.delenv("AI_FACTORY_RESEARCH_SEARCH_URL", raising=False)
    with pytest.raises(RuntimeError, match="AI_FACTORY_RESEARCH_SEARCH_URL"):
        search_public_web("validated improvement query")

    monkeypatch.setenv(
        "AI_FACTORY_RESEARCH_SEARCH_URL",
        "https://search.example.test/search",
    )

    class FakeResponse:
        status_code = 200

        def iter_bytes(self):
            yield b" " * 1_000_001

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def stream(self, *args, **kwargs):
            class ResponseContext:
                def __enter__(self):
                    return FakeResponse()

                def __exit__(self, *args):
                    return False

            return ResponseContext()

    monkeypatch.setattr("src.research_search.httpx.Client", FakeClient)
    with pytest.raises(RuntimeError, match="exceeded 1 MB"):
        search_public_web("validated improvement query")
