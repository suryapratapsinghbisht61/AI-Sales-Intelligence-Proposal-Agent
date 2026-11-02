import uuid

from langchain_text_splitters import RecursiveCharacterTextSplitter
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Document, DocumentChunk
from app.services import llm
from app.services.extract import extract
from app.services.storage import storage

EMBED_BATCH = 64


def process_document(db: Session, document_id: uuid.UUID, version: int) -> None:
    """Idempotent: re-running replaces this version's chunks rather than duplicating them."""
    doc = db.get(Document, document_id)
    if doc is None or doc.version != version:
        return  # deleted or superseded by a newer upload; nothing to do
    doc.status, doc.error = "processing", None
    db.commit()

    sections = extract(doc.filename, storage().get(doc.storage_key))
    s = get_settings()
    splitter = RecursiveCharacterTextSplitter(chunk_size=s.chunk_size, chunk_overlap=s.chunk_overlap)
    pieces = [(t, sec) for sec in sections for t in splitter.split_text(sec.text)]

    vectors = []
    for i in range(0, len(pieces), EMBED_BATCH):
        vectors += llm.embed_documents([t for t, _ in pieces[i : i + EMBED_BATCH]])

    db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == doc.id))
    db.add_all(
        DocumentChunk(
            org_id=doc.org_id,
            document_id=doc.id,
            version=version,
            ordinal=i,
            content=t,
            page=sec.page,
            section=sec.section,
            embedding=v,
        )
        for i, ((t, sec), v) in enumerate(zip(pieces, vectors, strict=True))
    )
    doc.status, doc.chunk_count = "ready", len(pieces)
    doc.text_preview = "\n\n".join(sec.text for sec in sections)[:4000]
    db.commit()
