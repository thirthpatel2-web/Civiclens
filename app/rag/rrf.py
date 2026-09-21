"""Reciprocal Rank Fusion.

RRF merges ranked lists without needing comparable scores (BM25 and cosine live on
different scales): ``score(d) = sum_over_lists weight / (k + rank_d)`` with rank
starting at 1. Ties are broken deterministically.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field


@dataclass(frozen=True)
class FusedHit:
    item_id: str
    score: float
    ranks: Mapping[str, int] = field(default_factory=dict)  # list name -> 1-based rank


def reciprocal_rank_fusion(
    rankings: Mapping[str, Sequence[str]],
    *,
    k: int = 60,
    weights: Mapping[str, float] | None = None,
) -> list[FusedHit]:
    if k <= 0:
        raise ValueError("k must be positive")
    scores: dict[str, float] = {}
    ranks: dict[str, dict[str, int]] = {}
    for name, ids in rankings.items():
        weight = 1.0 if weights is None else weights.get(name, 1.0)
        seen: set[str] = set()
        rank = 0
        for item in ids:
            if item in seen:  # a list must not count the same item twice
                continue
            seen.add(item)
            rank += 1
            scores[item] = scores.get(item, 0.0) + weight / (k + rank)
            ranks.setdefault(item, {})[name] = rank
    fused = [FusedHit(i, s, ranks[i]) for i, s in scores.items()]
    fused.sort(key=lambda h: (-h.score, min(h.ranks.values()), h.item_id))
    return fused
