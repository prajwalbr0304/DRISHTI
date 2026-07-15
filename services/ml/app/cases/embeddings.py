"""Embedder interface for semantic similar-case search (doc 02 §5).

Two backends behind one contract (mirrors the risk ModelInterface):

  * SentenceTransformerEmbedder — a real multilingual sentence-transformer
    (paraphrase-multilingual-mpnet-base-v2, 768-dim, EN + Kannada in one space).
    The doc-preferred encoder; used when `sentence-transformers` is importable
    and the weights load.
  * HashingEmbedder — a deterministic signed feature-hashing encoder (word tokens
    + char trigrams, Kannada-aware) into the same 768 dims, L2-normalised. Always
    available, no heavy deps, and — unlike the near-random datagen vectors — it
    produces MEANINGFUL cosine similarity (cases sharing crime type / charges / MO
    words land close). It is the robust fallback and the default when the ST model
    is not installed.

Both return L2-normalised float32 vectors so pgvector cosine distance (`<=>`,
the HNSW op class on CrimeEmbedding) is well-behaved. EMBED_DIM is kept in sync
with the vector(768) column and the ModelVersion.EmbeddingDim (doc 02 §5).
"""
from __future__ import annotations

import hashlib
import os
import re
from abc import ABC, abstractmethod

import numpy as np

EMBED_DIM = 768  # must match CrimeEmbedding.Embedding vector(768) + ModelVersion.EmbeddingDim

# Latin alphanumerics + the Kannada Unicode block (U+0C80–U+0CFF) so Kannada case
# text tokenises rather than being dropped.
_TOKEN_RE = re.compile(r"[0-9a-z\u0c80-\u0cff]+")


class Embedder(ABC):
    name: str = "abstract"
    version: str = "1.0.0"
    family: str = "abstract"
    dim: int = EMBED_DIM

    @abstractmethod
    def embed(self, texts: list[str]) -> np.ndarray:
        """Return an (n, dim) float32 array of L2-normalised row vectors."""


def _l2_normalise(mat: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (mat / norms).astype(np.float32)


class HashingEmbedder(Embedder):
    name = "drishti-embed-hashing"
    version = "1.0.0"
    family = "hashing"

    def __init__(self, dim: int = EMBED_DIM):
        self.dim = dim

    @staticmethod
    def _tokens(text: str) -> list[str]:
        text = (text or "").lower()
        words = _TOKEN_RE.findall(text)
        grams: list[str] = []
        for w in words:
            grams.append(w)
            if len(w) >= 4:  # char trigrams add morphological / multilingual robustness
                grams.extend(w[i:i + 3] for i in range(len(w) - 2))
        return grams

    def _vector(self, text: str) -> np.ndarray:
        v = np.zeros(self.dim, dtype=np.float32)
        for tok in self._tokens(text):
            digest = hashlib.md5(tok.encode("utf-8")).digest()
            idx = int.from_bytes(digest[:8], "little") % self.dim
            sign = 1.0 if digest[8] & 1 else -1.0
            v[idx] += sign
        return v

    def embed(self, texts: list[str]) -> np.ndarray:
        mat = np.vstack([self._vector(t) for t in texts]) if texts \
            else np.zeros((0, self.dim), dtype=np.float32)
        return _l2_normalise(mat)


class SentenceTransformerEmbedder(Embedder):
    """Real multilingual sentence-transformer (doc 02 §5's named encoder)."""
    family = "sentence-transformer"

    def __init__(self, model_id: str = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"):
        from sentence_transformers import SentenceTransformer  # raises if not installed
        self._model = SentenceTransformer(model_id)
        self.dim = int(self._model.get_sentence_embedding_dimension())
        if self.dim != EMBED_DIM:
            raise RuntimeError(
                f"{model_id} is {self.dim}-dim but CrimeEmbedding is vector({EMBED_DIM}); "
                "pick a 768-dim encoder or change the column + EmbeddingDim together.")
        self.name = "drishti-embed-mpnet"
        self.version = "1.0.0"

    def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        vecs = self._model.encode(texts, normalize_embeddings=True,
                                  convert_to_numpy=True, batch_size=64,
                                  show_progress_bar=False)
        return np.asarray(vecs, dtype=np.float32)


def get_embedder(name: str | None = None) -> Embedder:
    """Resolve the embedder.

    Order: explicit `name`/DRISHTI_EMBEDDER (mpnet|st|hashing) -> the real
    multilingual sentence-transformer if importable & loadable -> hashing.
    """
    choice = (name or os.getenv("DRISHTI_EMBEDDER", "")).strip().lower()
    if choice in ("hash", "hashing"):
        return HashingEmbedder()
    if choice in ("st", "mpnet", "sentence-transformer", "sentence-transformers"):
        return SentenceTransformerEmbedder()  # explicit request: let failures surface
    try:
        import sentence_transformers  # noqa: F401
        return SentenceTransformerEmbedder()
    except Exception:
        return HashingEmbedder()


def embedder_for_model_name(model_name: str) -> Embedder:
    """Reconstruct the embedder that produced a stored corpus (by ModelName), so a
    live query is embedded in the SAME space. Raises if it can't be rebuilt."""
    if model_name == HashingEmbedder.name:
        return HashingEmbedder()
    if model_name == "drishti-embed-mpnet":
        emb = SentenceTransformerEmbedder()
        if emb.name != model_name:  # pragma: no cover - defensive
            raise RuntimeError("resolved a different embedder than the corpus")
        return emb
    raise RuntimeError(
        f"corpus was embedded with unknown model '{model_name}'; cannot rebuild the query embedder")


def to_pgvector(vec) -> str:
    """Format a vector as a pgvector text literal: '[v1,v2,...]'."""
    return "[" + ",".join(f"{float(x):.6f}" for x in vec) + "]"
