"""Corpus embedding batch job (Phase 10 / doc 02 §5).

Embeds a corpus of cases with the resolved multilingual embedder and writes
CrimeEmbedding rows under a dedicated 'case' ModelVersion — so similar-case
search runs against a coherent, live vector space rather than the near-random
datagen 'brief_facts' vectors. Idempotent: clears prior rows for this embedding
ModelVersion before inserting, so a re-run fully refreshes the corpus.
"""
from __future__ import annotations

import hashlib
from typing import Optional

from psycopg2.extras import execute_values

from .. import models
from . import casedata
from .embeddings import get_embedder


def embed_corpus(conn, limit: Optional[int] = 12000, batch_size: int = 512,
                 embedder_name: Optional[str] = None) -> dict:
    """Embed up to `limit` cases (stratified by sub-head; None/0 = all) and write
    them to CrimeEmbedding. Returns a summary dict."""
    embedder = get_embedder(embedder_name)

    with conn.cursor() as cur:
        ids = casedata.select_corpus_case_ids(cur, limit)

    mv_id = models.get_or_create_model_version(
        conn, embedder.name, "embedding", embedder.version,
        framework=embedder.family, embedding_dim=embedder.dim,
        hyperparameters={"source_type": "case", "dim": embedder.dim,
                         "stratified_by": "CrimeMinorHeadID"},
        metrics={"corpus_target": len(ids)})

    # idempotent refresh: drop this model version's prior 'case' rows first
    with conn.cursor() as cur:
        cur.execute('DELETE FROM "CrimeEmbedding" '
                    'WHERE "ModelVersionID"=%s AND "SourceType"=\'case\'', (mv_id,))

    written = 0
    with conn.cursor() as cur:
        for i in range(0, len(ids), batch_size):
            recs = casedata.fetch_corpus_batch(cur, ids[i:i + batch_size])
            if not recs:
                continue
            vecs = embedder.embed([r["text"] for r in recs])
            rows = []
            for rec, vec in zip(recs, vecs):
                content = rec["text"][:2000]
                rows.append(("case", rec["case_id"], mv_id,
                             "[" + ",".join(f"{float(x):.6f}" for x in vec) + "]",
                             content, hashlib.md5(content.encode("utf-8")).hexdigest()))
            execute_values(
                cur,
                'INSERT INTO "CrimeEmbedding" '
                '("SourceType","CaseMasterID","ModelVersionID","Embedding","Content","ContentHash") '
                "VALUES %s",
                rows, template="(%s,%s,%s,%s::vector,%s,%s)", page_size=batch_size)
            written += len(rows)

    models.log_inference(
        conn, mv_id,
        inputs={"limit": limit, "embedder": embedder.name, "family": embedder.family},
        outputs={"embedded": written, "corpus_ids": len(ids)},
        ref_table="CrimeEmbedding")

    return {"embedded": written, "model": embedder.name, "family": embedder.family,
            "model_version_id": mv_id, "dim": embedder.dim, "corpus_ids": len(ids)}
