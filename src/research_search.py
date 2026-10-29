import html
import ipaddress
import json
import os
import re
from typing import Any
from urllib.parse import urlparse

import httpx


_MAX_RESPONSE_BYTES = 1_000_000
_MAX_RESULTS = 5
_TAG_PATTERN = re.compile(r"<[^>]*>")
_SPACE_PATTERN = re.compile(r"\s+")


def _configured_search_url() -> str:
    search_url = os.getenv("AI_FACTORY_RESEARCH_SEARCH_URL", "").strip()
    parsed = urlparse(search_url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise RuntimeError(
            "Set AI_FACTORY_RESEARCH_SEARCH_URL to a configured SearXNG /search endpoint."
        )
    return search_url


def _public_https_url(value: Any) -> bool:
    if not isinstance(value, str) or len(value) > 2048:
        return False
    parsed = urlparse(value)
    host = parsed.hostname
    if parsed.scheme != "https" or not host or parsed.username or parsed.password:
        return False
    if host.lower() == "localhost" or host.lower().endswith((".local", ".internal")):
        return False
    try:
        return ipaddress.ip_address(host).is_global
    except ValueError:
        return True


def _clean_snippet(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    text = html.unescape(_TAG_PATTERN.sub(" ", value))
    return _SPACE_PATTERN.sub(" ", text).strip()[:1500]


def search_public_web(query: str) -> list[dict[str, str]]:
    if not isinstance(query, str) or not 3 <= len(query.strip()) <= 200:
        raise ValueError("web search query must contain 3 to 200 characters")
    search_url = _configured_search_url()
    chunks = []
    received = 0
    try:
        with httpx.Client(timeout=10.0, follow_redirects=False) as client:
            with client.stream(
                "GET",
                search_url,
                params={"q": query.strip(), "format": "json", "categories": "general"},
                headers={"Accept": "application/json"},
            ) as response:
                if response.status_code < 200 or response.status_code >= 300:
                    raise RuntimeError(
                        f"Configured search provider returned HTTP {response.status_code}."
                    )
                for chunk in response.iter_bytes():
                    received += len(chunk)
                    if received > _MAX_RESPONSE_BYTES:
                        raise RuntimeError("Configured search provider response exceeded 1 MB.")
                    chunks.append(chunk)
    except httpx.HTTPError as exc:
        raise RuntimeError(
            f"Configured search provider request failed ({type(exc).__name__})."
        ) from exc

    try:
        payload = json.loads(b"".join(chunks))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Configured search provider returned invalid JSON.") from exc
    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list):
        raise RuntimeError("Configured search provider response omitted its results array.")

    leads = []
    seen_urls = set()
    for result in results:
        if not isinstance(result, dict) or not _public_https_url(result.get("url")):
            continue
        url = result["url"]
        if url in seen_urls:
            continue
        title = result.get("title")
        if not isinstance(title, str) or not title.strip():
            continue
        seen_urls.add(url)
        engine = result.get("engine", "search")
        leads.append(
            {
                "title": title.strip()[:300],
                "url": url,
                "snippet": _clean_snippet(
                    result.get("content", result.get("snippet", ""))
                ),
                "engine": engine[:80] if isinstance(engine, str) else "search",
            }
        )
        if len(leads) == _MAX_RESULTS:
            break
    return leads
