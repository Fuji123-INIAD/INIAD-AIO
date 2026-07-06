"""Deterministic local embedding fallback for context-card search."""

from __future__ import annotations

import hashlib
import math
import re
from typing import Iterable, Protocol


ASCII_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


class EmbeddingProvider(Protocol):
    name: str
    dimensions: int

    def embed(self, text: str) -> list[float]:
        """Return a deterministic vector for text."""


class HashedBagOfWordsEmbeddingProvider:
    """Small API-free embedding fallback based on hashed token counts."""

    name = "local-hashed-bow-v1"

    def __init__(self, dimensions: int = 64) -> None:
        self.dimensions = dimensions

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in tokenize_for_embedding(text):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        return normalize_vector(vector)


def tokenize_for_embedding(text: str) -> list[str]:
    normalized = str(text or "").casefold()
    tokens = ASCII_TOKEN_PATTERN.findall(normalized)
    compact = "".join(char for char in normalized if not char.isspace())
    if compact:
        tokens.extend(_character_ngrams(compact, n=2))
        tokens.extend(_character_ngrams(compact, n=3))
    return tokens


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right))


def normalize_vector(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


def build_vector_cache(
    documents: Iterable[dict[str, object]],
    *,
    provider: EmbeddingProvider | None = None,
) -> dict[str, object]:
    resolved_provider = provider or HashedBagOfWordsEmbeddingProvider()
    vectors = []
    for document in documents:
        text = str(document.get("text") or "")
        vectors.append(
            {
                "id": document.get("id"),
                "text": text,
                "vector": resolved_provider.embed(text),
            }
        )
    return {
        "provider": resolved_provider.name,
        "dimensions": resolved_provider.dimensions,
        "vectors": vectors,
    }


def _character_ngrams(value: str, *, n: int) -> list[str]:
    if len(value) < n:
        return [value] if value else []
    return [value[index : index + n] for index in range(0, len(value) - n + 1)]
