from __future__ import annotations

import hashlib
import math
import os
from collections import OrderedDict
from threading import Lock

from app.services.rag_deadline import check_deadline
from app.services.rag_observability import set_trace_attribute, timed_step


def cosine_similarity(left: list[float], right: list[float]) -> float:
    denominator = math.sqrt(sum(value * value for value in left)) * math.sqrt(
        sum(value * value for value in right)
    )
    if not denominator:
        return 0.0
    return sum(a * b for a, b in zip(left, right)) / denominator


class SemanticReranker:
    """Second passage sémantique, batché et observable."""

    def __init__(self, embed_model) -> None:
        self.embed_model = embed_model
        self._cache: OrderedDict[str, list[float]] = OrderedDict()
        self._cache_lock = Lock()
        self._cache_size = int(os.getenv("RAG_EMBEDDING_CACHE_SIZE", "512"))

    def _cache_key(self, text: str) -> str:
        model = str(getattr(self.embed_model, "model_name", "unknown"))
        return f"{model}:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"

    def _cached(self, text: str) -> list[float] | None:
        if self._cache_size <= 0:
            return None
        key = self._cache_key(text)
        with self._cache_lock:
            vector = self._cache.get(key)
            if vector is not None:
                self._cache.move_to_end(key)
            return vector

    def _store(self, text: str, vector: list[float]) -> None:
        if self._cache_size <= 0:
            return
        key = self._cache_key(text)
        with self._cache_lock:
            self._cache[key] = vector
            self._cache.move_to_end(key)
            while len(self._cache) > self._cache_size:
                self._cache.popitem(last=False)

    def _semantic_vectors(self, question: str, nodes: list) -> tuple[list[float], list[list[float]]]:
        texts = [question, *(node.get_content() for node in nodes)]
        vectors: list[list[float] | None] = [None] * len(texts)
        missing_indexes = []

        # Réutilise les vecteurs Qdrant si le vector store les a joints aux nodes.
        for index, node in enumerate(nodes, start=1):
            embedded = getattr(getattr(node, "node", None), "embedding", None)
            if isinstance(embedded, (list, tuple)) and embedded:
                vectors[index] = list(embedded)

        for index, text in enumerate(texts):
            if vectors[index] is not None:
                continue
            cached = self._cached(text)
            if cached is None:
                missing_indexes.append(index)
            else:
                vectors[index] = cached

        if missing_indexes:
            missing_texts = [texts[index] for index in missing_indexes]
            with timed_step("semantic_embedding", itemCount=len(missing_texts)):
                embedded = self.embed_model.get_text_embedding_batch(missing_texts)
            for index, vector in zip(missing_indexes, embedded):
                vectors[index] = vector
                self._store(texts[index], vector)

        set_trace_attribute("semanticCandidateCount", len(nodes))
        set_trace_attribute("semanticReencodedCount", len(missing_indexes))
        set_trace_attribute("semanticCachedCount", len(texts) - len(missing_indexes))
        return vectors[0], vectors[1:]  # type: ignore[return-value]

    def rerank(self, question: str, nodes: list, lexical_score, intent_score) -> list:
        return [node for _, node, _ in self.score_nodes(
            question, nodes, lexical_score, intent_score,
        )]

    def score_nodes(self, question: str, nodes: list, lexical_score, intent_score) -> list:
        if not nodes:
            return []
        try:
            with timed_step("candidate_preparation", candidateCount=len(nodes)):
                contents = [node.get_content() for node in nodes]
            if len(nodes) < 2:
                semantic_scores = [float(nodes[0].score or 0.0)]
            else:
                question_vector, candidate_vectors = self._semantic_vectors(question, nodes)
                with timed_step("semantic_similarity", candidateCount=len(nodes)):
                    semantic_scores = [
                        cosine_similarity(question_vector, vector)
                        for vector in candidate_vectors
                    ]
            with timed_step("lexical_score", candidateCount=len(nodes)):
                lexical_scores = [lexical_score(question, node) for node in nodes]
            with timed_step("intent_score", candidateCount=len(nodes)):
                intent_scores = [intent_score(question, content) for content in contents]
            with timed_step("final_reranking", candidateCount=len(nodes)):
                scored = []
                for node, semantic, lexical, intent in zip(
                    nodes, semantic_scores, lexical_scores, intent_scores
                ):
                    vector_score = float(node.score or 0.0)
                    combined = (
                        0.45 * vector_score + 0.35 * semantic
                        + 0.14 * lexical + 0.06 * intent
                    )
                    scored.append((combined, node, {
                        "vector_score": vector_score,
                        "semantic_score": semantic,
                        "lexical_score": lexical,
                        "intent_score": intent,
                    }))
                return sorted(scored, key=lambda item: item[0], reverse=True)
        except Exception:
            check_deadline("semantic_reranking")
            with timed_step("reranker_fallback", candidateCount=len(nodes)):
                return [
                    (
                        float(node.score or 0.0), node,
                        {
                            "vector_score": float(node.score or 0.0),
                            "semantic_score": None,
                            "lexical_score": lexical_score(question, node),
                            "intent_score": intent_score(question, node.get_content()),
                        },
                    )
                    for node in sorted(
                        nodes, key=lambda item: float(item.score or 0.0), reverse=True
                    )
                ]
