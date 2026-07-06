from __future__ import annotations

import unittest

from backend.app.core.embeddings import (
    HashedBagOfWordsEmbeddingProvider,
    build_vector_cache,
    cosine_similarity,
)


class EmbeddingFallbackTests(unittest.TestCase):
    def test_hashed_embedding_is_deterministic_and_normalized(self) -> None:
        provider = HashedBagOfWordsEmbeddingProvider(dimensions=16)

        first = provider.embed("security privacy")
        second = provider.embed("security privacy")

        self.assertEqual(first, second)
        self.assertAlmostEqual(1.0, cosine_similarity(first, second), places=6)

    def test_vector_cache_records_provider_and_document_vectors(self) -> None:
        cache = build_vector_cache(
            [
                {"id": "resource-1", "text": "security card"},
                {"id": "resource-2", "text": "assignment card"},
            ],
            provider=HashedBagOfWordsEmbeddingProvider(dimensions=8),
        )

        self.assertEqual("local-hashed-bow-v1", cache["provider"])
        self.assertEqual(8, cache["dimensions"])
        self.assertEqual(2, len(cache["vectors"]))
        self.assertEqual("resource-1", cache["vectors"][0]["id"])
        self.assertEqual(8, len(cache["vectors"][0]["vector"]))


if __name__ == "__main__":
    unittest.main()
