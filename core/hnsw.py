"""Pure-Python HNSW (Hierarchical Navigable Small World) vector index.

No numpy required -- operates on list[float] vectors with cosine similarity.
"""

from __future__ import annotations

import heapq
import json
import math
import random
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Node:
    """A node in the HNSW graph."""
    id: int
    vector: list[float]
    metadata: dict[str, Any]
    neighbors: dict[int, list[int]] = field(default_factory=dict)
    # neighbors[level] -> list of neighbor node ids


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _norm(a: list[float]) -> float:
    return math.sqrt(sum(x * x for x in a))


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    na = _norm(a)
    nb = _norm(b)
    if na == 0.0 or nb == 0.0:
        return 0.0
    return _dot(a, b) / (na * nb)


def cosine_distance(a: list[float], b: list[float]) -> float:
    """Cosine distance = 1 - cosine_similarity."""
    return 1.0 - cosine_similarity(a, b)


class HNSWIndex:
    """Simple HNSW index for approximate nearest-neighbor search.

    Parameters:
        m: Max number of connections per node per level.
        ef_construction: Size of dynamic candidate list during build.
        ml: Level multiplier (controls expected max level).
    """

    def __init__(self, m: int = 16, ef_construction: int = 200, ml: float = 0.36) -> None:
        self.m = m
        self.ef_construction = ef_construction
        self.ml = ml
        self._nodes: dict[int, Node] = {}
        self._entry_point: int | None = None
        self._max_level: int = 0
        self._next_id: int = 0

    def _random_level(self) -> int:
        level = 0
        while random.random() < self.ml and level < 32:
            level += 1
        return level

    def _search_layer(self, query: list[float], entry_id: int, ef: int,
                      level: int) -> list[tuple[float, int]]:
        """Search a single layer, returning ef nearest neighbors as (dist, id)."""
        visited: set[int] = {entry_id}
        entry_dist = cosine_distance(query, self._nodes[entry_id].vector)
        candidates: list[tuple[float, int]] = [(entry_dist, entry_id)]
        # Max-heap for worst elements (negate distance for max-heap behavior)
        results: list[tuple[float, int]] = [(-entry_dist, entry_id)]

        while candidates:
            dist_c, c_id = heapq.heappop(candidates)
            worst_dist = -results[0][0]
            if dist_c > worst_dist:
                break

            node = self._nodes[c_id]
            neighbor_ids = node.neighbors.get(level, [])
            for n_id in neighbor_ids:
                if n_id in visited:
                    continue
                visited.add(n_id)
                n_dist = cosine_distance(query, self._nodes[n_id].vector)
                worst_dist = -results[0][0]
                if n_dist < worst_dist or len(results) < ef:
                    heapq.heappush(candidates, (n_dist, n_id))
                    heapq.heappush(results, (-n_dist, n_id))
                    if len(results) > ef:
                        heapq.heappop(results)

        return [(abs(d), nid) for d, nid in results]

    def _select_neighbors(self, query: list[float], candidates: list[tuple[float, int]],
                          m: int) -> list[int]:
        """Select the m closest neighbors from candidates."""
        candidates.sort(key=lambda x: x[0])
        return [nid for _, nid in candidates[:m]]

    def add(self, vector: list[float], metadata: dict[str, Any] | None = None) -> int:
        """Add a vector to the index. Returns the assigned node id."""
        node_id = self._next_id
        self._next_id += 1
        level = self._random_level()
        node = Node(id=node_id, vector=vector, metadata=metadata or {})
        for lv in range(level + 1):
            node.neighbors[lv] = []
        self._nodes[node_id] = node

        if self._entry_point is None:
            self._entry_point = node_id
            self._max_level = level
            return node_id

        # Traverse from top to the node's level
        current = self._entry_point
        for lv in range(self._max_level, level, -1):
            results = self._search_layer(vector, current, ef=1, level=lv)
            current = min(results, key=lambda x: x[0])[1]

        # Insert at each level from node's level down to 0
        for lv in range(min(level, self._max_level), -1, -1):
            candidates = self._search_layer(vector, current, ef=self.ef_construction, level=lv)
            neighbors = self._select_neighbors(vector, candidates, self.m)
            node.neighbors[lv] = neighbors

            # Bidirectional links
            for n_id in neighbors:
                n_node = self._nodes[n_id]
                if lv not in n_node.neighbors:
                    n_node.neighbors[lv] = []
                n_node.neighbors[lv].append(node_id)
                # Prune if too many neighbors
                if len(n_node.neighbors[lv]) > self.m:
                    # Keep closest
                    dists = [
                        (cosine_distance(n_node.vector, self._nodes[nb].vector), nb)
                        for nb in n_node.neighbors[lv]
                    ]
                    n_node.neighbors[lv] = self._select_neighbors(n_node.vector, dists, self.m)

            if candidates:
                current = min(candidates, key=lambda x: x[0])[1]

        if level > self._max_level:
            self._max_level = level
            self._entry_point = node_id

        return node_id

    def search(self, query_vector: list[float], k: int = 5) -> list[tuple[int, float, dict[str, Any]]]:
        """Search for k nearest neighbors.

        Returns list of (node_id, similarity_score, metadata) sorted by similarity descending.
        """
        if self._entry_point is None:
            return []

        current = self._entry_point
        for lv in range(self._max_level, 0, -1):
            results = self._search_layer(query_vector, current, ef=1, level=lv)
            current = min(results, key=lambda x: x[0])[1]

        candidates = self._search_layer(query_vector, current,
                                        ef=max(k, self.ef_construction), level=0)
        candidates.sort(key=lambda x: x[0])
        results = []
        for dist, nid in candidates[:k]:
            sim = 1.0 - dist
            results.append((nid, sim, self._nodes[nid].metadata))
        return results

    def save(self, path: str) -> None:
        """Serialize the index to a JSON file."""
        data = {
            "m": self.m,
            "ef_construction": self.ef_construction,
            "ml": self.ml,
            "entry_point": self._entry_point,
            "max_level": self._max_level,
            "next_id": self._next_id,
            "nodes": {
                str(nid): {
                    "vector": node.vector,
                    "metadata": node.metadata,
                    "neighbors": {str(lv): nbrs for lv, nbrs in node.neighbors.items()},
                }
                for nid, node in self._nodes.items()
            },
        }
        with open(path, "w") as f:
            json.dump(data, f)

    @classmethod
    def load(cls, path: str) -> HNSWIndex:
        """Deserialize an index from a JSON file."""
        with open(path) as f:
            data = json.load(f)
        idx = cls(m=data["m"], ef_construction=data["ef_construction"], ml=data["ml"])
        idx._entry_point = data["entry_point"]
        idx._max_level = data["max_level"]
        idx._next_id = data["next_id"]
        for nid_str, ndata in data["nodes"].items():
            nid = int(nid_str)
            node = Node(
                id=nid,
                vector=ndata["vector"],
                metadata=ndata["metadata"],
                neighbors={int(lv): nbrs for lv, nbrs in ndata["neighbors"].items()},
            )
            idx._nodes[nid] = node
        return idx

    def __len__(self) -> int:
        return len(self._nodes)
