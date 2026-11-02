"""The one place company knowledge is searched. Tenant + current-version filters are applied in SQL,
before anything reaches a model."""

import uuid
from dataclasses import asdict, dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Document, DocumentChunk
from app.services import llm

RRF_K = 60


@dataclass
class Hit:
    chunk_id: str
    document_id: str
    title: str
    category: str
    page: int | None
    section: str | None
    content: str
    score: float

    def citation(self) -> dict:
        d = asdict(self)
        d["excerpt"] = d.pop("content")[:500]
        return d


def _base(org_id: uuid.UUID, categories: list[str] | None):
    q = (
        select(DocumentChunk, Document.title, Document.category)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(
            DocumentChunk.org_id == org_id,
            Document.org_id == org_id,
            Document.status == "ready",
            DocumentChunk.version == Document.version,  # replaced versions never surface
        )
    )
    return q.where(Document.category.in_(categories)) if categories else q


def search(
    db: Session, org_id: uuid.UUID, query: str, k: int = 6, categories: list[str] | None = None,
    semantic: bool = True,
) -> list[Hit]:
    """Hybrid search: pgvector cosine + Postgres full-text, fused with reciprocal rank fusion."""
    pool = max(k * 3, 20)
    ranked: list[list] = []
    tsq = func.websearch_to_tsquery("english", query)
    ranked.append(
        db.execute(
            _base(org_id, categories)
            .where(DocumentChunk.tsv.op("@@")(tsq))
            .order_by(func.ts_rank_cd(DocumentChunk.tsv, tsq).desc())
            .limit(pool)
        ).all()
    )
    if semantic:
        qv = llm.embed_query(query)
        ranked.append(
            db.execute(
                _base(org_id, categories).order_by(DocumentChunk.embedding.cosine_distance(qv)).limit(pool)
            ).all()
        )
    scores: dict = {}
    rows: dict = {}
    for lst in ranked:
        for rank, row in enumerate(lst):
            cid = row[0].id
            scores[cid] = scores.get(cid, 0) + 1 / (RRF_K + rank + 1)
            rows[cid] = row
    top = sorted(scores, key=scores.get, reverse=True)[:k]
    return [
        Hit(
            chunk_id=str(c.id), document_id=str(c.document_id), title=title, category=cat,
            page=c.page, section=c.section, content=c.content, score=round(scores[c.id], 5),
        )
        for c, title, cat in (rows[cid] for cid in top)
    ]
