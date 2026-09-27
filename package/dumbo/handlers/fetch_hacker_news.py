"""Fetch live top stories from the Hacker News Firebase API (no API key)."""

from __future__ import annotations

import json
import urllib.error
from datetime import datetime, timezone
from typing import Any, Dict, List

from ..lib.demo_http import fetch_json, tool_error, tool_ok
from ..lib.describe import describe_document


class FetchHackerNews:
    def describe(self, payload=None):
        return describe_document(
            "fetch_hacker_news",
            "Hacker News top stories",
            "Live tech headlines and scores from the Hacker News Firebase API.",
            {
                "limit": {
                    "type": "integer",
                    "title": "Limit",
                    "description": "Number of top stories to return.",
                    "minimum": 1,
                    "maximum": 20,
                    "default": 5,
                },
            },
            output_schema={
                "type": "object",
                "properties": {
                    "source": {"type": "string"},
                    "fetched_at": {"type": "string", "format": "date-time"},
                    "count": {"type": "integer"},
                    "stories": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "integer"},
                                "title": {"type": "string"},
                                "url": {"type": "string"},
                                "score": {"type": "integer"},
                                "by": {"type": "string"},
                                "comments": {"type": "integer"},
                            },
                        },
                    },
                },
            },
        )

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        action = "fetch_hacker_news"
        try:
            limit = int(payload.get("limit") or 5)
        except (TypeError, ValueError):
            limit = 5
        limit = max(1, min(limit, 20))

        try:
            story_ids = fetch_json("https://hacker-news.firebaseio.com/v0/topstories.json")
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
            return tool_error(f"HN API request failed: {exc}", action=action, payload=payload)

        if not isinstance(story_ids, list):
            return tool_error("Unexpected HN API response", action=action, payload=payload)

        stories: List[Dict[str, Any]] = []
        for sid in story_ids[:limit]:
            try:
                item = fetch_json(f"https://hacker-news.firebaseio.com/v0/item/{sid}.json")
            except Exception:
                continue
            if not isinstance(item, dict):
                continue
            stories.append(
                {
                    "id": item.get("id"),
                    "title": item.get("title"),
                    "url": item.get("url") or f"https://news.ycombinator.com/item?id={item.get('id')}",
                    "score": item.get("score"),
                    "by": item.get("by"),
                    "comments": item.get("descendants"),
                }
            )

        return tool_ok(
            action,
            payload,
            {
                "source": "Hacker News Firebase API",
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "count": len(stories),
                "stories": stories,
            },
        )
