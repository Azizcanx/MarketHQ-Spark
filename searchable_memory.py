# -*- coding: utf-8 -*-
"""Phase J5 — Searchable Memory.

Extends research_memory_query_adapter_v1 with full-text search
across research memory entries.

Search dimensions:
- symbol
- timeframe
- regime
- setup
- agent
- hypothesis
- claim
- date
- failure
- evidence
- experiment
"""

from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class SearchField(Enum):
    SYMBOL = "symbol"
    TIMEFRAME = "timeframe"
    REGIME = "regime"
    SETUP = "setup"
    AGENT = "agent"
    HYPOTHESIS = "hypothesis"
    CLAIM = "claim"
    DATE = "date"
    FAILURE = "failure"
    EVIDENCE = "evidence"
    EXPERIMENT = "experiment"
    TEXT = "text"
    MEMORY_TYPE = "memory_type"
    STATUS = "status"


@dataclass
class SearchQuery:
    """A search query against research memory."""
    query_id: str = ""
    terms: list[str] = field(default_factory=list)
    fields: list[str] = field(default_factory=list)
    filters: dict[str, Any] = field(default_factory=dict)
    limit: int = 50
    offset: int = 0
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.query_id:
            now = datetime.now(timezone.utc).isoformat()
            self.query_id = f"QRY-{hashlib.sha256(now.encode()).hexdigest()[:8].upper()}"
            if not self.created_at:
                self.created_at = now

    def to_dict(self) -> dict[str, Any]:
        return {
            "query_id": self.query_id,
            "terms": self.terms,
            "fields": self.fields,
            "filters": self.filters,
            "limit": self.limit,
            "offset": self.offset,
            "created_at": self.created_at,
        }


@dataclass
class SearchResult:
    """A single search result."""
    memory_id: str = ""
    memory_type: str = ""
    text: str = ""
    relevance_score: float = 0.0
    matched_fields: list[str] = field(default_factory=list)
    regime: str = ""
    asset: str = ""
    timeframe: str = ""
    status: str = ""
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "memory_id": self.memory_id,
            "memory_type": self.memory_type,
            "text": self.text[:200],
            "relevance_score": self.relevance_score,
            "matched_fields": self.matched_fields,
            "regime": self.regime,
            "asset": self.asset,
            "timeframe": self.timeframe,
            "status": self.status,
            "created_at": self.created_at,
        }


@dataclass
class SearchResponse:
    """Full search response."""
    query: SearchQuery
    results: list[SearchResult] = field(default_factory=list)
    total_count: int = 0
    returned_count: int = 0
    query_time_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query.to_dict(),
            "results": [r.to_dict() for r in self.results],
            "total_count": self.total_count,
            "returned_count": self.returned_count,
            "query_time_ms": round(self.query_time_ms, 2),
        }


def _tokenize(text: str) -> list[str]:
    """Split text into lowercase tokens."""
    if not text:
        return []
    return re.findall(r'\w+', text.lower())


def _score_match(
    query_tokens: list[str],
    text: str,
    field_boost: float = 1.0,
) -> float:
    """Score how well query tokens match text."""
    if not query_tokens:
        return 0.0
    text_tokens = set(_tokenize(text))
    if not text_tokens:
        return 0.0
    matches = sum(1 for t in query_tokens if t in text_tokens)
    return (matches / len(query_tokens)) * field_boost


BOOSTS = {
    "text": 1.0,
    "regime": 1.5,
    "asset": 2.0,
    "timeframe": 1.5,
    "status": 1.0,
    "memory_type": 1.5,
    "claim": 2.0,
    "hypothesis": 2.0,
    "experiment": 1.5,
    "evidence": 1.0,
    "setup": 1.5,
    "agent": 1.5,
}


class SearchableMemory:
    """Searchable research memory with provenance tracking."""

    def __init__(self, memory_store: list[dict[str, Any]] | None = None) -> None:
        self._memory: list[dict[str, Any]] = memory_store or []
        self._search_history: list[SearchQuery] = []

    def add_entry(self, entry: dict[str, Any]) -> None:
        """Add a memory entry for search."""
        self._memory.append(entry)

    def add_entries(self, entries: list[dict[str, Any]]) -> None:
        """Add multiple memory entries."""
        self._memory.extend(entries)

    def search(
        self,
        query: str,
        fields: list[str] | None = None,
        filters: dict[str, Any] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> SearchResponse:
        """Search memory entries.

        Args:
            query: Search terms (space-separated)
            fields: Fields to search in (empty = all text fields)
            filters: Key-value filters to apply
            limit: Max results
            offset: Pagination offset

        Returns:
            SearchResponse with ranked results
        """
        start = time.time()
        query_tokens = _tokenize(query)
        if not query_tokens:
            empty_q = SearchQuery(terms=[], fields=fields or [])
            return SearchResponse(
                query=empty_q,
                results=[],
                total_count=0,
                returned_count=0,
                query_time_ms=(time.time() - start) * 1000,
            )

        search_fields = fields or ["text", "regime", "asset", "timeframe", "status", "memory_type"]

        candidates = self._memory
        if filters:
            for key, value in filters.items():
                candidates = [
                    e for e in candidates
                    if str(e.get(key, "")).lower() == str(value).lower()
                ]

        scored: list[tuple[dict[str, Any], float, list[str]]] = []
        for entry in candidates:
            total_score = 0.0
            matched: list[str] = []
            for field_name in search_fields:
                field_text = str(entry.get(field_name, ""))
                if not field_text:
                    continue
                boost = BOOSTS.get(field_name, 1.0)
                score = _score_match(query_tokens, field_text, boost)
                if score > 0:
                    total_score += score
                    matched.append(field_name)

            if total_score > 0:
                scored.append((entry, total_score, matched))

        scored.sort(key=lambda x: x[1], reverse=True)
        paginated = scored[offset:offset + limit]

        results = [
            SearchResult(
                memory_id=str(e.get("memory_id", e.get("id", ""))),
                memory_type=str(e.get("memory_type", e.get("type", ""))),
                text=str(e.get("text", e.get("observation", ""))),
                relevance_score=s,
                matched_fields=m,
                regime=str(e.get("regime", "")),
                asset=str(e.get("asset", e.get("symbol", ""))),
                timeframe=str(e.get("timeframe", "")),
                status=str(e.get("status", "")),
                created_at=str(e.get("created_at", "")),
            )
            for e, s, m in paginated
        ]

        elapsed = (time.time() - start) * 1000

        response = SearchResponse(
            query=SearchQuery(
                terms=query_tokens,
                fields=search_fields,
                filters=filters or {},
                limit=limit,
                offset=offset,
            ),
            results=results,
            total_count=len(scored),
            returned_count=len(results),
            query_time_ms=elapsed,
        )

        self._search_history.append(response.query)
        return response

    def get_entry(self, memory_id: str) -> dict[str, Any] | None:
        """Get a specific memory entry by ID."""
        for entry in self._memory:
            eid = str(entry.get("memory_id", entry.get("id", "")))
            if eid == memory_id:
                return entry
        return None

    def count(self) -> int:
        """Total entries in memory."""
        return len(self._memory)

    def get_search_history(self) -> list[SearchQuery]:
        """Get search history."""
        return list(self._search_history)

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_count": self.count(),
            "search_history_count": len(self._search_history),
            "recent_searches": [q.to_dict() for q in self._search_history[-10:]],
        }