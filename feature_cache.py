# -*- coding: utf-8 -*-
"""Feature Snapshot Cache — deterministic, bounded, invalidatable.

Cache key: (symbol, timeframe, data_cutoff_timestamp)
Same key → same snapshot. Different cutoff → different snapshot.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any

from agent_contract import FeatureSnapshot, MarketContext


class FeatureSnapshotCache:
    """In-memory cache for FeatureSnapshots.

    Attributes:
        max_size: Maximum number of entries (LRU eviction).
        hits: Cache hit counter.
        misses: Cache miss counter.
        invalidations: Invalidation counter.
    """

    def __init__(self, max_size: int = 100) -> None:
        self._cache: OrderedDict[tuple[str, str, str], FeatureSnapshot] = OrderedDict()
        self.max_size = max_size
        self.hits = 0
        self.misses = 0
        self.invalidations = 0

    def get(
        self, symbol: str, timeframe: str, cutoff: str
    ) -> FeatureSnapshot | None:
        """Get a snapshot by cache key."""
        key = (symbol, timeframe, cutoff)
        if key in self._cache:
            self._cache.move_to_end(key)
            self.hits += 1
            return self._cache[key]
        self.misses += 1
        return None

    def get_by_context(self, ctx: MarketContext) -> FeatureSnapshot | None:
        """Get a snapshot using MarketContext cache key."""
        return self.get(ctx.symbol, ctx.timeframe, ctx.data_cutoff_timestamp)

    def put(
        self, symbol: str, timeframe: str, cutoff: str, snapshot: FeatureSnapshot
    ) -> None:
        """Store a snapshot. Evicts LRU entry if over max_size."""
        key = (symbol, timeframe, cutoff)
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = snapshot
        if len(self._cache) > self.max_size:
            self._cache.popitem(last=False)

    def invalidate(self, symbol: str | None = None, timeframe: str | None = None) -> int:
        """Invalidate entries matching filters. Returns count removed."""
        keys_to_remove = []
        for key in self._cache:
            sym, tf, _ = key
            if symbol and sym != symbol:
                continue
            if timeframe and tf != timeframe:
                continue
            keys_to_remove.append(key)

        for key in keys_to_remove:
            del self._cache[key]
            self.invalidations += 1

        return len(keys_to_remove)

    def invalidate_all(self) -> int:
        """Clear all cache entries."""
        count = len(self._cache)
        self._cache.clear()
        self.invalidations += count
        return count

    def get_stats(self) -> dict[str, int | float]:
        """Get cache statistics."""
        total = self.hits + self.misses
        hit_rate = self.hits / total if total > 0 else 0.0
        return {
            "size": len(self._cache),
            "max_size": self.max_size,
            "hits": self.hits,
            "misses": self.misses,
            "invalidations": self.invalidations,
            "hit_rate": round(hit_rate, 4),
        }

    def clear_stats(self) -> None:
        """Reset hit/miss/invalidation counters."""
        self.hits = 0
        self.misses = 0
        self.invalidations = 0


# Global default cache
_default_cache = FeatureSnapshotCache()


def get_default_cache() -> FeatureSnapshotCache:
    """Get the global default cache."""
    return _default_cache


def get_cache(symbol: str, timeframe: str, cutoff: str) -> FeatureSnapshot | None:
    """Get from global cache."""
    return _default_cache.get(symbol, timeframe, cutoff)


def put_cache(
    symbol: str, timeframe: str, cutoff: str, snapshot: FeatureSnapshot
) -> None:
    """Put to global cache."""
    _default_cache.put(symbol, timeframe, cutoff, snapshot)