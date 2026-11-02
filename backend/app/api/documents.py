import hashlib
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import Document, Job
from app.security import Ctx, ctx, get_owned
from app.services import jobs
from app.services.audit import audit
from app.services.extract import ExtractionError, validate_bytes
from app.services.storage import storage

router = APIRouter(prefix="/documents", tags=["documents"])

CATEGORIES = ("product_docs", "pricing", "case_studies", "sales_playbooks", "proposals", "service_descriptions",
              "policies", "competitor_research", "other")
Category = Literal[CATEGORIES]  # type: ignore[valid-type]


def doc_out(d: Document, preview: bool = False) -> dict:
    out = {k: getattr(d, k) for k in ("title", "filename", "content_type", "size_bytes", "category", "tags",
                                       "version", "status", "error", "chunk_count", "created_at", "updated_at")}
    out["id"] = str(d.id)
    if preview:
        out["text_preview"] = d.text_preview
    return out


async def _read_upload(file: UploadFile) -> tuple[bytes, str]:
    limit = get_settings().max_upload_mb * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, f"File is larger than {get_settings().max_upload_mb} MB")
    if not data:
        raise HTTPException(400, "File is empty")
    try:
        return data, validate_bytes(file.filename or "", data)
    except ExtractionError as e:
        raise HTTPException(415, str(e)) from None


def _store_and_queue(db: Session, c: Ctx, d: Document, data: bytes) -> None:
    d.storage_key = f"{c.org_id}/{d.id}/v{d.version}"
    storage().put(d.storage_key, data, d.content_type)
    jobs.enqueue(db, c.org_id, "ingest", document_id=d.id, version=d.version)


@router.post("", status_code=201)
async def upload(file: UploadFile = File(...), title: str = Form(""), category: Category = Form("other"),
                 tags: str = Form(""), c: Ctx = Depends(ctx), db: Session = Depends(get_db)):
    data, ctype = await _read_upload(file)
    sha = hashlib.sha256(data).hexdigest()
    dup = db.scalar(select(Document).where(Document.org_id == c.org_id, Document.sha256 == sha))
    if dup:
        raise HTTPException(409, f"This file was already uploaded as '{dup.title}'")
    d = Document(id=uuid.uuid4(), org_id=c.org_id, title=(title.strip() or file.filename)[:300],
                 filename=file.filename[:300], content_type=ctype, size_bytes=len(data), sha256=sha,
                 category=category, tags=[t.strip() for t in tags.split(",") if t.strip()][:20],
                 uploaded_by=c.user.id, storage_key="", version=1)
    db.add(d)
    _store_and_queue(db, c, d, data)
    audit(db, c.org_id, c.user.id, "document.uploaded", d, filename=d.filename)
    db.commit()
    return doc_out(d)


@router.get("")
def list_docs(q: str = "", category: str = "", status: str = "", limit: int = 50, offset: int = 0,
              c: Ctx = Depends(ctx), db: Session = Depends(get_db)):
    stmt = select(Document).where(Document.org_id == c.org_id)
    if q:
        stmt = stmt.where(or_(Document.title.ilike(f"%{q}%"), Document.filename.ilike(f"%{q}%")))
    if category:
        stmt = stmt.where(Document.category == category)
    if status:
        stmt = stmt.where(Document.status == status)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(Document.created_at.desc()).limit(min(limit, 200)).offset(offset)).all()
    return {"items": [doc_out(d) for d in rows], "total": total}


@router.get("/{doc_id}")
def get_doc(doc_id: uuid.UUID, c: Ctx = Depends(ctx), db: Session = Depends(get_db)):
    return doc_out(get_owned(db, Document, doc_id, c), preview=True)


@router.get("/{doc_id}/status")
def doc_status(doc_id: uuid.UUID, c: Ctx = Depends(ctx), db: Session = Depends(get_db)):
    d = get_owned(db, Document, doc_id, c)
    return {"status": d.status, "error": d.error, "chunk_count": d.chunk_count}


@router.get("/{doc_id}/download")
def download(doc_id: uuid.UUID, c: Ctx = Depends(ctx), db: Session = Depends(get_db)):
    d = get_owned(db, Document, doc_id, c)
    return Response(storage().get(d.storage_key), media_type=d.content_type,
                    headers={"Content-Disposition": f'attachment; filename="{d.filename}"',
                             "X-Content-Type-Options": "nosniff"})


class DocPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    category: Category | None = None
    tags: list[str] | None = Field(default=None, max_length=20)


def _can_manage(c: Ctx, d: Document) -> None:
    if d.uploaded_by != c.user.id:
        c.require("documents.manage_any")


@router.patch("/{doc_id}")
def update_doc(doc_id: uuid.UUID, body: DocPatch, c: Ctx = Depends(ctx), db: Session = Depends(get_db)):
    d = get_owned(db, Document, doc_id, c)
    _can_manage(c, d)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(d, k, v)
    db.commit()
    return doc_out(d)


@router.post("/{doc_id}/replace")
async def replace(doc_id: uuid.UUID, file: UploadFile = File(...), c: Ctx = Depends(ctx),
                  db: Session = Depends(get_db)):
    d = get_owned(db, Document, doc_id, c)
    _can_manage(c, d)
    data, ctype = await _read_upload(file)
    old_key = d.storage_key
    d.version += 1  # old chunks stop matching Document.version immediately, so they leave retrieval
    d.filename, d.content_type, d.size_bytes = file.filename[:300], ctype, len(data)
    d.sha256, d.status, d.error, d.chunk_count = hashlib.sha256(data).hexdigest(), "uploaded", None, 0
    _store_and_queue(db, c, d, data)
    audit(db, c.org_id, c.user.id, "document.replaced", d, version=d.version)
    db.commit()
    storage().delete(old_key)
    return doc_out(d)


@router.post("/{doc_id}/retry")
def retry(doc_id: uuid.UUID, c: Ctx = Depends(ctx), db: Session = Depends(get_db)):
    d = get_owned(db, Document, doc_id, c)
    if d.status != "failed":
        raise HTTPException(409, "Only failed documents can be retried")
    d.status, d.error = "uploaded", None
    jobs.enqueue(db, c.org_id, "ingest", document_id=d.id, version=d.version)
    db.commit()
    return doc_out(d)


@router.delete("/{doc_id}", status_code=204)
def delete_doc(doc_id: uuid.UUID, c: Ctx = Depends(ctx), db: Session = Depends(get_db)):
    d = get_owned(db, Document, doc_id, c)
    _can_manage(c, d)
    key = d.storage_key
    audit(db, c.org_id, c.user.id, "document.deleted", d, filename=d.filename)
    db.delete(d)  # chunks cascade
    db.query(Job).filter(Job.kind == "ingest", Job.status == "queued",
                         Job.payload["document_id"].astext == str(doc_id)).delete(synchronize_session=False)
    db.commit()
    storage().delete(key)
