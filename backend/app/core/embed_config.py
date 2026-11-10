import os
import time

from llama_index.embeddings.ollama import OllamaEmbedding
from ollama import Client

from app.services.rag_deadline import operation_timeout
from app.services.rag_observability import record_embedding_call


EMBEDDING_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
EMBEDDING_REQUEST_TIMEOUT = float(os.getenv("OLLAMA_EMBEDDING_TIMEOUT_SECONDS", "60"))
EMBEDDING_BATCH_SIZE = int(os.getenv("OLLAMA_EMBEDDING_BATCH_SIZE", "32"))
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "30m")
OLLAMA_NUM_THREAD = int(os.getenv("OLLAMA_NUM_THREAD", "3"))


class ObservableOllamaEmbedding(OllamaEmbedding):
    """OllamaEmbedding batché avec timeout borné par la deadline courante."""

    request_timeout: float = EMBEDDING_REQUEST_TIMEOUT
    keep_alive: str = OLLAMA_KEEP_ALIVE

    def _get_text_embeddings(self, texts: list[str]) -> list[list[float]]:
        # La version installée de llama-index-embeddings-ollama boucle ici texte
        # par texte. L'API Ollama /api/embed accepte réellement une liste : un
        # batch remplace donc N appels HTTP séquentiels sans changer le modèle.
        return self.get_general_text_embeddings(texts)

    def get_general_text_embeddings(self, texts: list[str]) -> list[list[float]]:
        timeout = operation_timeout(self.request_timeout, "semantic_embedding")
        started = time.perf_counter_ns()
        error = None
        client = Client(host=self.base_url, timeout=timeout)
        try:
            response = client.embed(
                model=self.model_name,
                input=texts,
                options=self.ollama_additional_kwargs,
                keep_alive=self.keep_alive,
            )
            if isinstance(response, dict):
                return response["embeddings"]
            return response.embeddings
        except Exception as exc:
            error = exc
            raise
        finally:
            elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
            record_embedding_call(
                call_name="embedding_batch",
                model=self.model_name,
                item_count=len(texts),
                elapsed_ms=elapsed_ms,
                error=error,
            )
            close = getattr(client, "close", None)
            if close is not None:
                close()

    def get_general_text_embedding(self, text: str) -> list[float]:
        return self.get_general_text_embeddings([text])[0]


def get_embed_model():
    return ObservableOllamaEmbedding(
        model_name=EMBEDDING_MODEL,
        base_url=os.getenv("OLLAMA_URL", "http://localhost:11434"),
        embed_batch_size=EMBEDDING_BATCH_SIZE,
        keep_alive=OLLAMA_KEEP_ALIVE,
        request_timeout=EMBEDDING_REQUEST_TIMEOUT,
        ollama_additional_kwargs={"num_thread": OLLAMA_NUM_THREAD},
    )
