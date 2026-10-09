"""tools.py - STUDENT IMPLEMENTS.  Source tools for the research agents.   Guide: GUIDE.md, part 1.

Rules for every tool:
  * runs on the HOST (not in the sandbox): API keys must never enter the sandbox;
  * returns a STRING (JSON text of compact records) and NEVER raises:
        "NO RESULTS"  when the source answers with nothing,
        "ERROR: ..."  when the source keeps failing after the retries (the agent then tries another source);
  * the docstring is the tool description the LLM reads: keep it precise (what it does, what it returns, when to use it).
Try your tools without any agent:   python tools.py
"""
import json
import os
import random
import re
import threading
import time
import urllib.parse
import xml.etree.ElementTree as ET

import httpx  # noqa: F401
from langchain_core.tools import tool

# ---- constants (given) ----
ARXIV_URL = "https://export.arxiv.org/api/query"  # https only: http answers 301
HF_DAILY_URL = "https://huggingface.co/api/daily_papers"
HF_SEARCH_URL = "https://huggingface.co/api/papers/search"
EXA_URL = "https://mcp.exa.ai/mcp"


class RetryableError(Exception):
    """Given. Raise it inside a call to ask with_retry to wait and try again (retry_after in seconds, optional)."""

    def __init__(self, message, retry_after=None):
        super().__init__(message)
        self.retry_after = retry_after


# ---- TODO 1: retry helper ----
def with_retry(fn, *, attempts=5, base=1.0, cap=30.0):
    """Call fn(); when it raises RetryableError, wait and call it again.

    PSEUDO-CODE:
      for attempt in 0 .. attempts-1:
          try: return fn()
          except RetryableError as e:
              if this was the last attempt: raise
              delay = e.retry_after if the server told us, else exponential backoff base * 2**attempt
              cap the delay at `cap` seconds; add random jitter to the exponential case
              sleep(delay)
    Use it to wrap EVERY network call below. Also treat these as retryable: HTTP 429/500/502/503/504,
    httpx.TransportError (timeouts, connection resets). Read the Retry-After header when present.
    """
    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    if base < 0 or cap < 0:
        raise ValueError("base and cap must be non-negative")

    for attempt in range(attempts):
        try:
            return fn()
        except RetryableError as exc:
            if attempt == attempts - 1:
                raise
            if exc.retry_after is not None:
                delay = min(cap, max(0.0, float(exc.retry_after)))
            else:
                # Add jitter so clients that failed together do not retry together.
                delay = min(cap, base * (2**attempt) + random.uniform(0.0, base))
            time.sleep(delay)


_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
_ARXIV_LOCK = threading.Lock()
_ARXIV_LAST_CALL = 0.0


def _retry_after(response: httpx.Response):
    """Return Retry-After seconds when the header contains the supported numeric form."""
    value = response.headers.get("Retry-After")
    if value is None:
        return None
    try:
        return max(0.0, float(value.strip()))
    except (TypeError, ValueError):
        return None


def _request(method: str, url: str, **kwargs) -> httpx.Response:
    """Make one HTTP request, translating only transient failures into RetryableError."""
    try:
        response = httpx.request(method, url, timeout=30.0, follow_redirects=False, **kwargs)
    except httpx.TransportError as exc:
        raise RetryableError(str(exc)) from exc
    if response.status_code in _RETRYABLE_STATUS_CODES:
        raise RetryableError(
            f"HTTP {response.status_code} for {response.request.url}",
            retry_after=_retry_after(response),
        )
    response.raise_for_status()
    return response


def _clean_text(value, limit=None) -> str:
    text = " ".join(str(value or "").split())
    return text[:limit] if limit is not None else text


def _error_text(exc: Exception, secret: str = "") -> str:
    message = f"{type(exc).__name__}: {exc}"
    if secret:
        message = message.replace(secret, "[REDACTED]")
        message = message.replace(urllib.parse.quote(secret, safe=""), "[REDACTED]")
    # Also protects a key if an HTTP library reformats the query string.
    message = re.sub(r"(?i)(exaApiKey=)[^&\s'\"]+", r"\1[REDACTED]", message)
    return f"ERROR: {message}"


def _bounded_int(value, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, int(value)))


def _wait_for_arxiv_slot() -> None:
    global _ARXIV_LAST_CALL
    with _ARXIV_LOCK:
        delay = 3.0 - (time.monotonic() - _ARXIV_LAST_CALL)
        if delay > 0:
            time.sleep(delay)
        _ARXIV_LAST_CALL = time.monotonic()


# ---- TODO 2: arXiv ----
@tool
def arxiv_search(query: str, max_results: int = 10) -> str:
    """Search arXiv papers by keywords, newest first. Returns a JSON list of {id, url, published, title, summary}."""
    # PSEUDO-CODE:
    #   keep only word characters of `query` -> terms; no terms -> "NO RESULTS" (do not call the network)
    #   respect arXiv etiquette: at least 3 seconds between two arXiv calls (remember the time of the last call)
    #   GET ARXIV_URL params: search_query="all:t1 AND all:t2 ...", sortBy=submittedDate, sortOrder=descending,
    #       max_results=clamp(max_results, 1, 30)           (wrap in with_retry)
    #   parse the Atom XML: each <entry> -> {id (last part of <id> after /abs/), url, published[:10], title, summary}
    #       collapse whitespace/newlines in title and summary; cut summary to ~600 chars
    #   no entries -> "NO RESULTS"; else json.dumps(records, ensure_ascii=False)
    #   any exception -> "ERROR: <type>: <message>"
    try:
        # Treat punctuation and boolean syntax as separators, not as arXiv syntax.
        # [^\W_] is a Unicode letter/digit without underscore; hyphens are allowed inside a term.
        terms = re.findall(r"[^\W_]+(?:-[^\W_]+)*", str(query or ""), flags=re.UNICODE)
        terms = [term for term in terms if term.upper() not in {"AND", "OR", "NOT"}]
        if not terms:
            return "NO RESULTS"

        params = {
            "search_query": " AND ".join(f"all:{term}" for term in terms),
            "sortBy": "submittedDate",
            "sortOrder": "descending",
            "max_results": _bounded_int(max_results, 1, 30),
            "start": 0,
        }

        def fetch():
            _wait_for_arxiv_slot()
            return _request("GET", ARXIV_URL, params=params)

        response = with_retry(fetch, attempts=7, base=2.0, cap=60.0)
        root = ET.fromstring(response.content)
        namespace = {"atom": "http://www.w3.org/2005/Atom"}
        records = []
        for entry in root.findall("atom:entry", namespace):
            raw_id = _clean_text(entry.findtext("atom:id", default="", namespaces=namespace))
            paper_id = raw_id.rsplit("/", 1)[-1]
            paper_id = re.sub(r"v\d+$", "", paper_id)
            if not paper_id:
                continue
            published = _clean_text(entry.findtext("atom:published", default="", namespaces=namespace))
            records.append(
                {
                    "id": paper_id,
                    "url": f"https://arxiv.org/abs/{paper_id}",
                    "published": published[:10],
                    "title": _clean_text(entry.findtext("atom:title", default="", namespaces=namespace)),
                    "summary": _clean_text(
                        entry.findtext("atom:summary", default="", namespaces=namespace), 600
                    ),
                }
            )
        return json.dumps(records, ensure_ascii=False) if records else "NO RESULTS"
    except Exception as exc:
        return _error_text(exc)


# ---- TODO 3: Hugging Face ----
@tool
def hf_daily_papers(limit: int = 30, date: str = "", keyword: str = "") -> str:
    """Hugging Face Daily Papers = what is trending in AI research. Returns a JSON list of
    {id, url, published, title, summary, upvotes, github, stars} sorted by upvotes. `date` is YYYY-MM-DD (empty = latest).
    `keyword` filters title/summary; there is no topic search on this endpoint (use hf_search_papers for a topic)."""
    # PSEUDO-CODE:
    #   GET HF_DAILY_URL params: limit (clamp 1..100) and date (only when given)      (with_retry)
    #   response = list of items {"paper": {id, title, summary, upvotes, githubRepo, githubStars, publishedAt}, ...}
    #   map every item to the record shape above (skip items without paper.id); url = https://huggingface.co/papers/<id>
    #   keyword -> keep records whose title+summary contains it (case-insensitive); sort by upvotes descending
    try:
        params = {"limit": _bounded_int(limit, 1, 100)}
        if date:
            params["date"] = str(date)
        response = with_retry(lambda: _request("GET", HF_DAILY_URL, params=params))
        records = _hf_records(response.json(), prefer_ai_summary=False)
        needle = _clean_text(keyword).casefold()
        if needle:
            records = [
                record
                for record in records
                if needle in f"{record['title']} {record['summary']}".casefold()
            ]
        records.sort(key=lambda record: record["upvotes"], reverse=True)
        return json.dumps(records, ensure_ascii=False) if records else "NO RESULTS"
    except Exception as exc:
        return _error_text(exc)


@tool
def hf_search_papers(query: str, limit: int = 10) -> str:
    """Search Hugging Face papers by topic. Returns a JSON list of
    {id, url, published, title, summary, upvotes, github, stars}."""
    # PSEUDO-CODE:
    #   GET HF_SEARCH_URL params: q=query, limit (clamp 1..50)                         (with_retry)
    #   same item shape as the daily endpoint; prefer paper["ai_summary"] over paper["summary"] when present
    try:
        query = _clean_text(query)
        if not query:
            return "NO RESULTS"
        params = {"q": query, "limit": _bounded_int(limit, 1, 50)}
        response = with_retry(lambda: _request("GET", HF_SEARCH_URL, params=params))
        records = _hf_records(response.json(), prefer_ai_summary=True)
        return json.dumps(records, ensure_ascii=False) if records else "NO RESULTS"
    except Exception as exc:
        return _error_text(exc)


def _hf_records(payload, *, prefer_ai_summary: bool) -> list[dict]:
    if isinstance(payload, dict):
        for key in ("papers", "items", "results"):
            if isinstance(payload.get(key), list):
                payload = payload[key]
                break
    if not isinstance(payload, list):
        raise ValueError("Hugging Face returned an unexpected response shape")

    records = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        paper = item.get("paper")
        if not isinstance(paper, dict) or not paper.get("id"):
            continue

        def field(name, default=""):
            value = paper.get(name)
            return item.get(name, default) if value is None else value

        summary = field("ai_summary") if prefer_ai_summary else ""
        if not summary:
            summary = field("summary")
        published = _clean_text(field("publishedAt"))
        paper_id = str(paper["id"])
        try:
            upvotes = int(field("upvotes", 0) or 0)
        except (TypeError, ValueError):
            upvotes = 0
        try:
            stars = int(field("githubStars", 0) or 0)
        except (TypeError, ValueError):
            stars = 0
        records.append(
            {
                "id": paper_id,
                "url": f"https://huggingface.co/papers/{paper_id}",
                "published": published[:10],
                "title": _clean_text(field("title")),
                "summary": _clean_text(summary, 600),
                "upvotes": upvotes,
                "github": field("githubRepo") or "",
                "stars": stars,
            }
        )
    return records


# ---- TODO 4: web search / fetch through the Exa MCP endpoint ----
@tool
def web_search(query: str, objective: str = "", num_results: int = 5) -> str:
    """Search the web (Exa). Describe the ideal page in natural language. Returns clean text of the top results with URLs."""
    # PSEUDO-CODE:
    #   call the MCP tool "web_search_exa" with arguments {query, objective, numResults}
    #       (objective is REQUIRED by Exa: when empty, build one from the query)
    #   see GUIDE.md part 1.4 for how to call an MCP server over plain HTTP (JSON-RPC "tools/call") and read the answer
    #   read optional env EXA_API_KEY; when present it is sent to the Exa endpoint.
    #       (see GUIDE.md 1.4 for where it goes) => the key then appears in exception text: redact it before returning "ERROR: ..."
    #   WATCH OUT: read GUIDE.md 1.4 about how Exa signals "rate limited" on the free tier, and retry on it
    api_key = os.getenv("EXA_API_KEY", "").strip()
    try:
        query = _clean_text(query)
        if not query:
            return "NO RESULTS"
        arguments = {
            "query": query,
            "objective": _clean_text(objective) or f"Find reliable sources about {query}",
            "numResults": _bounded_int(num_results, 1, 10),
        }
        text = _exa_call("web_search_exa", arguments, api_key=api_key)
        return text if text.strip() else "NO RESULTS"
    except Exception as exc:
        return _error_text(exc, api_key)


@tool
def web_fetch(url: str) -> str:
    """Read the full content of one web page (e.g. an arXiv abstract page) as markdown. Long pages are truncated."""
    # PSEUDO-CODE: MCP tool "web_fetch_exa" with arguments {"urls": [url]}; truncate the text to ~12000 chars
    api_key = os.getenv("EXA_API_KEY", "").strip()
    try:
        url = str(url or "").strip()
        if not url:
            return "NO RESULTS"
        text = _exa_call("web_fetch_exa", {"urls": [url]}, api_key=api_key)
        text = text[:12000]
        return text if text.strip() else "NO RESULTS"
    except Exception as exc:
        return _error_text(exc, api_key)


def _exa_call(tool_name: str, arguments: dict, *, api_key: str = "") -> str:
    endpoint = EXA_URL
    if api_key:
        endpoint = f"{endpoint}?{urllib.parse.urlencode({'exaApiKey': api_key})}"
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
    }
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }

    def invoke():
        response = _request("POST", endpoint, headers=headers, json=payload)
        envelope = _parse_mcp_response(response.text)
        if "error" in envelope:
            raise RuntimeError(f"Exa JSON-RPC error: {envelope['error']}")
        result = envelope.get("result")
        if not isinstance(result, dict):
            raise ValueError("Exa response has no result object")
        if _exa_is_rate_limited(result.get("_meta")):
            raise RetryableError("Exa rate limit reached")
        content = result.get("content", [])
        texts = [
            part.get("text", "")
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        ]
        return "\n\n".join(text for text in texts if text)

    return with_retry(invoke, attempts=8, base=2.0, cap=60.0)


def _parse_mcp_response(body: str) -> dict:
    # MCP servers may answer as SSE (possibly with several events) or plain JSON.
    events = []
    for line in body.splitlines():
        if line.startswith("data:"):
            data = line[5:].strip()
            if data and data != "[DONE]":
                events.append(json.loads(data))
    if events:
        for event in reversed(events):
            if isinstance(event, dict) and ("result" in event or "error" in event):
                return event
        raise ValueError("Exa SSE response contains no JSON-RPC result")
    parsed = json.loads(body)
    if not isinstance(parsed, dict):
        raise ValueError("Exa returned an unexpected JSON response")
    return parsed


def _exa_is_rate_limited(meta) -> bool:
    if not meta:
        return False
    marker = json.dumps(meta, ensure_ascii=False, default=str).casefold()
    return any(
        phrase in marker
        for phrase in ("rate limit", "rate_limit", "ratelimit", "too many requests", '"429"')
    )


# ---- TODO 5: registry (the researcher subagent gets exactly these) ----
SOURCE_TOOLS = [arxiv_search, hf_daily_papers, hf_search_papers, web_search, web_fetch]


if __name__ == "__main__":
    for name, fn, args in [
        ("arxiv_search", arxiv_search, {"query": "world model", "max_results": 3}),
        ("hf_daily_papers", hf_daily_papers, {"limit": 20}),
        ("hf_search_papers", hf_search_papers, {"query": "world model", "limit": 3}),
        ("web_search", web_search, {"query": "survey paper on world models", "num_results": 2}),
        ("web_fetch", web_fetch, {"url": "https://arxiv.org/abs/1803.10122"}),
    ]:
        try:
            print(f"== {name}\n{fn.invoke(args)[:400]}\n")
        except NotImplementedError as exc:
            print(f"== {name}: not implemented yet ({exc})\n")
