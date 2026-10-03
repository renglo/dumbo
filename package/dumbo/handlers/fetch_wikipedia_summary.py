"""Fetch a live Wikipedia page summary (REST API, no API key)."""

from __future__ import annotations

import json
import urllib.error
from datetime import datetime, timezone
from typing import Any, Dict
from urllib.parse import quote

from ..lib.demo_http import fetch_json, tool_error, tool_ok
from ..lib.describe import describe_document


class FetchWikipediaSummary:
    def describe(self, payload=None):
        return describe_document(
            "fetch_wikipedia_summary",
            "Wikipedia summary",
            "Live Wikipedia lead summary for an article title or topic. topic is accepted as an alias of title.",
            {
                "title": {
                    "type": "string",
                    "title": "Article title",
                    "description": "Wikipedia article title or topic. Alias: topic.",
                },
            },
            required=["title"],
            output_schema={
                "type": "object",
                "properties": {
                    "source": {"type": "string"},
                    "fetched_at": {"type": "string", "format": "date-time"},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "extract": {"type": "string"},
                    "page_url": {"type": "string"},
                },
            },
        )

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        action = "fetch_wikipedia_summary"
        title = str(payload.get("title") or payload.get("topic") or "").strip()
        if not title:
            return tool_error("title is required (Wikipedia article title or topic)", action=action, payload=payload)

        encoded = quote(title.replace(" ", "_"), safe="")
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded}"

        try:
            doc = fetch_json(url)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                resolved = self._resolve_title(title)
                if resolved and resolved != title:
                    return self.run({**payload, "title": resolved})
                return tool_error(f"No Wikipedia article found for '{title}'", action=action, payload=payload)
            return tool_error(f"Wikipedia API HTTP {exc.code}", action=action, payload=payload)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
            return tool_error(f"Wikipedia API request failed: {exc}", action=action, payload=payload)

        if not isinstance(doc, dict):
            return tool_error("Unexpected Wikipedia API response", action=action, payload=payload)

        resolved_title = doc.get("title") or title
        return tool_ok(
            action,
            payload,
            {
                "source": "Wikipedia REST API",
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "title": resolved_title,
                "description": doc.get("description"),
                "extract": doc.get("extract"),
                "page_url": (doc.get("content_urls") or {}).get("desktop", {}).get("page"),
            },
        )

    @staticmethod
    def _resolve_title(query: str) -> str | None:
        """Best-effort title via MediaWiki opensearch (no API key)."""
        q = quote(query.strip())
        url = (
            "https://en.wikipedia.org/w/api.php"
            f"?action=opensearch&search={q}&limit=1&namespace=0&format=json"
        )
        try:
            data = fetch_json(url)
        except Exception:
            return None
        if not isinstance(data, list) or len(data) < 2:
            return None
        titles = data[1]
        if isinstance(titles, list) and titles:
            top = str(titles[0]).strip()
            if top and _title_matches_query(query, top):
                return top
        return None


def _title_matches_query(query: str, title: str) -> bool:
    q = query.lower()
    t = title.lower()
    q_compact = q.replace(" ", "")
    t_compact = t.replace(" ", "")
    if q_compact and q_compact in t_compact:
        return True
    words = [w for w in q.split() if len(w) > 3]
    return any(w in t for w in words)
