'''
File:   dense.py
Brief:  Embeddings (bge-m3) with a text-hash cache.
Author: Demetrius242
Date:   2026-11-26
Version: v0.1.0

Chunk vectors are computed once per chunk text (keyed by its sha256) and
cached across rebuilds, so editing a dictionary or the chunker does not
re-embed the whole corpus. All query variants of one request are encoded
in a single batch. The model loads lazily; any failure degrades the
service to BM25 (the service reports the mode in /health).
'''

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)


class DenseIndex:
    '''Embedding model plus the persistent chunk-vector cache.'''

    def __init__(self, model_name: str, cache_dir: Path, device: str = "auto") -> None:
        '''Initialise (the model itself loads lazily on first encode).

        Args:
            model_name: Sentence-transformers model id ("none" disables).
            cache_dir: Directory of the per-model hash cache.
            device: "auto" | "cpu" | "cuda".
        '''
        self.model_name = model_name
        self.device = device
        self.cache_dir = cache_dir
        self._model = None
        self.cache_path = cache_dir / _safe_name(model_name) / "vectors.npz"
        self._cache_hashes: np.ndarray | None = None
        self._cache_vectors: np.ndarray | None = None
        self._load_cache()

    @property
    def available(self) -> bool:
        '''True when the model is loaded (or loads successfully).'''
        return self._ensure_model() is not None

    def _ensure_model(self):  # noqa: ANN202 - returns the ST model or None
        '''Load the sentence-transformers model once, or give up quietly.'''
        if self._model is not None:
            return self._model
        try:
            from sentence_transformers import SentenceTransformer

            device = self.device
            if device == "auto":
                import torch

                device = "cuda" if torch.cuda.is_available() else "cpu"
            self._model = SentenceTransformer(self.model_name, device=device)
        except Exception as exc:  # noqa: BLE001 - any failure → BM25-only
            logger.warning("embedding model unavailable (%s): %s", self.model_name, exc)
            self._model = None
        return self._model

    def _load_cache(self) -> None:
        '''Load the persisted hash→vector cache if it exists.'''
        if not self.cache_path.is_file():
            return
        try:
            data = np.load(self.cache_path)
            self._cache_hashes = data["hashes"]
            self._cache_vectors = data["vectors"]
        except (OSError, ValueError, KeyError) as exc:
            logger.warning("embedding cache unreadable: %s", exc)
            self._cache_hashes = None
            self._cache_vectors = None

    def _save_cache(self) -> None:
        '''Persist the cache atomically enough for a hackathon wall.'''
        if self._cache_hashes is None or self._cache_vectors is None:
            return
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.cache_path.with_suffix(".npz.tmp")
        np.savez_compressed(
            tmp,
            hashes=self._cache_hashes,
            vectors=self._cache_vectors,
        )
        tmp.replace(self.cache_path)

    def embed_texts(
        self, texts: list[str], use_cache: bool = True
    ) -> np.ndarray | None:
        '''Embed texts, reusing cached vectors for known text hashes.

        Args:
            texts: Texts to embed.
            use_cache: Read/write the persistent cache.

        Returns:
            Matrix aligned with *texts* (float32, normalised), or None when
            the model is unavailable.
        '''
        model = self._ensure_model()
        if model is None or not texts:
            return None
        hashes = np.array([_hash_text(t) for t in texts])
        result: np.ndarray | None = None
        cache_ready = (
            use_cache
            and self._cache_hashes is not None
            and self._cache_vectors is not None
        )
        if cache_ready:
            lookup = {h: i for i, h in enumerate(self._cache_hashes.tolist())}
            missing_idx = [i for i, h in enumerate(hashes.tolist()) if h not in lookup]
            if not missing_idx:
                rows = [lookup[h] for h in hashes.tolist()]
                result = self._cache_vectors[rows]
            else:
                fresh = model.encode(
                    [texts[i] for i in missing_idx],
                    batch_size=32,
                    normalize_embeddings=True,
                    show_progress_bar=False,
                    convert_to_numpy=True,
                ).astype(np.float32)
                self._cache_hashes = np.concatenate(
                    [self._cache_hashes, hashes[missing_idx]]
                )
                self._cache_vectors = np.concatenate([self._cache_vectors, fresh])
                self._save_cache()
                lookup = {h: i for i, h in enumerate(self._cache_hashes.tolist())}
                rows = [lookup[h] for h in hashes.tolist()]
                result = self._cache_vectors[rows]
        else:
            result = model.encode(
                texts,
                batch_size=32,
                normalize_embeddings=True,
                show_progress_bar=False,
                convert_to_numpy=True,
            ).astype(np.float32)
            if use_cache:
                self._cache_hashes = hashes
                self._cache_vectors = result
                self._save_cache()
        return result

    def encode_queries(self, queries: list[str]) -> np.ndarray | None:
        '''Encode query variants in one batch (no cache interaction).

        Args:
            queries: Query texts.

        Returns:
            Normalised matrix, or None when the model is unavailable.
        '''
        model = self._ensure_model()
        if model is None or not queries:
            return None
        return model.encode(
            queries,
            batch_size=len(queries),
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        ).astype(np.float32)


def _hash_text(text: str) -> str:
    '''Stable hash key for one text (aligned with chunk text_hash).'''
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _safe_name(model_name: str) -> str:
    '''Make a model id filesystem-safe.'''
    return "".join(ch if ch.isalnum() or ch in "-._" else "_" for ch in model_name)


__all__: list[str] = ["DenseIndex"]
