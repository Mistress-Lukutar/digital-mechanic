'''
File:   bm25.py
Brief:  Self-contained BM25 (Lucene formula) with engine-mask scoring.
Author: Demetrius242
Date:   2026-11-26
Version: v0.1.0

Plan-B names bm25s as the primary and a numpy implementation as the
fallback; the installed bm25s build did not survive a save/load roundtrip
(vocabulary and score state are lost), so the fallback became the primary.
The corpus is tiny (≈1.5k chunks): one CSR matrix in memory, saved as npz.

Scores are normalised into [0, 1] by the query's IDF sum — a coverage-like
relevance comparable across queries, used for the tier decision in
BM25-only mode.
'''

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from scipy import sparse

from rag.index.tokenizer import tokenize

K1 = 1.5
B = 0.75


@dataclass
class BM25Index:
    '''BM25 index: CSR term-frequency matrix plus metadata.'''

    vocab: dict[str, int] = field(default_factory=dict)
    idf: dict[str, float] = field(default_factory=dict)
    doc_mask_engines: dict[str, np.ndarray] = field(default_factory=dict)
    n_docs: int = 0
    avg_len: float = 0.0
    _tf: sparse.csr_matrix | None = None
    _doc_len: np.ndarray | None = None
    _idf_vec: np.ndarray | None = None

    # -- build ----------------------------------------------------------------

    @classmethod
    def build(
        cls,
        token_lists: list[list[str]],
        engine_lists: list[list[str]],
    ) -> BM25Index:
        '''Build the index from pre-tokenised chunks.

        Args:
            token_lists: Tokens per chunk (:func:`rag.index.tokenizer.tokenize`).
            engine_lists: Engine models per chunk.

        Returns:
            Built index.
        '''
        vocab: dict[str, int] = {}
        rows: list[int] = []
        cols: list[int] = []
        data: list[float] = []
        for doc_idx, tokens in enumerate(token_lists):
            counts: dict[int, int] = {}
            for token in tokens:
                col = vocab.setdefault(token, len(vocab))
                counts[col] = counts.get(col, 0) + 1
            for col, count in counts.items():
                rows.append(doc_idx)
                cols.append(col)
                data.append(float(count))
        shape = (len(token_lists), max(len(vocab), 1))
        tf = sparse.csr_matrix(
            (np.array(data, dtype=np.float32),
             (np.array(rows, dtype=np.int32), np.array(cols, dtype=np.int32))),
            shape=shape,
        )
        doc_len = np.asarray(tf.sum(axis=1)).ravel()
        n = len(token_lists)
        df = np.asarray((tf > 0).sum(axis=0)).ravel()
        idf_vec = np.log(1.0 + (n - df + 0.5) / (df + 0.5)).astype(np.float32)
        idf = {
            token: float(idf_vec[col]) for token, col in vocab.items()
        }

        masks: dict[str, np.ndarray] = {}
        engine_values = [set(engines) for engines in engine_lists]
        engines_all = sorted(set().union(*engine_values)) if engine_values else []
        for engine in engines_all:
            masks[engine] = np.array(
                [engine in engines for engines in engine_values], dtype=bool
            )
        return cls(
            vocab=vocab,
            idf=idf,
            doc_mask_engines=masks,
            n_docs=n,
            avg_len=float(doc_len.mean()) if n else 0.0,
            _tf=tf,
            _doc_len=doc_len,
            _idf_vec=idf_vec,
        )

    # -- scoring --------------------------------------------------------------

    def scores(
        self, query: str, mask: np.ndarray | None = None
    ) -> np.ndarray:
        '''Raw BM25 (Lucene) scores of every chunk against *query*.

        Args:
            query: Raw query text.
            mask: Optional float mask (1.0 = allowed); disallowed chunks
                score 0.

        Returns:
            Float array of length n_docs.
        '''
        if self._tf is None or self._doc_len is None or self._idf_vec is None:
            return np.zeros(self.n_docs, dtype=np.float32)
        tokens = tokenize(query)
        ids: list[int] = []
        for token in tokens:
            col = self.vocab.get(token)
            if col is not None:
                ids.append(col)
        if not ids:
            return np.zeros(self.n_docs, dtype=np.float32)
        tf_slice = np.asarray(
            self._tf[:, ids].todense(), dtype=np.float32
        )  # (n_docs, k)
        norm = K1 * (1.0 - B + B * self._doc_len / max(self.avg_len, 1e-6))
        weights = tf_slice * (K1 + 1.0) / (tf_slice + norm[:, None])
        raw = weights @ self._idf_vec[ids]
        if mask is not None:
            raw = raw * np.asarray(mask, dtype=np.float32)
        return raw.astype(np.float32)

    def normalized(
        self, query: str, mask: np.ndarray | None = None
    ) -> np.ndarray:
        '''Query-IDF coverage of each chunk, in [0, 1].

        Raw BM25 saturates near its ceiling for full matches, so the
        reported (comparable) score is the share of the query's IDF mass
        present in the chunk: 5 matched terms of 5 → 1.0, 3 of 5 → ~0.6.
        Ranking still uses :meth:`scores`; this number drives the tier.

        Args:
            query: Raw query text.
            mask: Optional float mask of allowed chunks.

        Returns:
            Coverage scores in [0, 1].
        '''
        if self._tf is None or self._doc_len is None or self._idf_vec is None:
            return np.zeros(self.n_docs, dtype=np.float32)
        tokens = tokenize(query)
        ids: list[int] = []
        seen: set[int] = set()
        for token in tokens:
            col = self.vocab.get(token)
            if col is not None and col not in seen:
                seen.add(col)
                ids.append(col)
        if not ids:
            return np.zeros(self.n_docs, dtype=np.float32)
        ceiling = float(sum(self._idf_vec[i] for i in ids))
        if ceiling <= 0:
            return np.zeros(self.n_docs, dtype=np.float32)
        present = np.asarray(
            (self._tf[:, ids] > 0).todense(), dtype=np.float32
        )  # (n_docs, k)
        coverage = (present @ self._idf_vec[ids]) / ceiling
        if mask is not None:
            coverage = coverage * np.asarray(mask, dtype=np.float32)
        return np.clip(coverage, 0.0, 1.0).astype(np.float32)

    # -- persistence ----------------------------------------------------------

    def save(self, directory: Path) -> None:
        '''Persist the index into *directory*.

        Args:
            directory: Target directory (created if missing).
        '''
        directory.mkdir(parents=True, exist_ok=True)
        if self._tf is not None:
            sparse.save_npz(directory / "tf.npz", self._tf)
        if self._doc_len is not None:
            np.save(directory / "doc_len.npy", self._doc_len)
        if self._idf_vec is not None:
            np.save(directory / "idf_vec.npy", self._idf_vec)
        meta = {
            "n_docs": self.n_docs,
            "avg_len": self.avg_len,
            "vocab": self.vocab,
            "idf": self.idf,
            "doc_engines": {
                engine: mask.astype(int).tolist()
                for engine, mask in self.doc_mask_engines.items()
            },
        }
        (directory / "meta.json").write_text(
            json.dumps(meta, ensure_ascii=False), encoding="utf-8"
        )

    @classmethod
    def load(cls, directory: Path) -> BM25Index:
        '''Load an index saved by :meth:`save`.

        Args:
            directory: Directory with tf.npz / doc_len.npy / idf_vec.npy /
                meta.json.

        Returns:
            Loaded index.

        Raises:
            FileNotFoundError: When the directory is not a saved index.
        '''
        meta_path = directory / "meta.json"
        if not meta_path.is_file():
            raise FileNotFoundError(f"not a saved BM25 index: {directory}")
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        tf_path = directory / "tf.npz"
        tf = sparse.load_npz(tf_path) if tf_path.is_file() else None
        doc_len_path = directory / "doc_len.npy"
        doc_len = np.load(doc_len_path) if doc_len_path.is_file() else None
        idf_path = directory / "idf_vec.npy"
        idf_vec = np.load(idf_path) if idf_path.is_file() else None
        masks = {
            engine: np.array(values, dtype=bool)
            for engine, values in meta["doc_engines"].items()
        }
        return cls(
            vocab={str(k): int(v) for k, v in meta["vocab"].items()},
            idf={str(k): float(v) for k, v in meta["idf"].items()},
            doc_mask_engines=masks,
            n_docs=int(meta["n_docs"]),
            avg_len=float(meta["avg_len"]),
            _tf=tf,
            _doc_len=doc_len,
            _idf_vec=idf_vec,
        )


__all__: list[str] = ["BM25Index"]
