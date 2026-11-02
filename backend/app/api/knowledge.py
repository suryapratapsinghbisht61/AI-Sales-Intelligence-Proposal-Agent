import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Conversation, Message, WorkflowRun
from app.security import Ctx, ctx, get_owned
from app.services import retrieval
from app.services.audit import audit
from app.services.llm import LLMNotConfigured, Run
from app.workflows import qa

router = APIRouter(tags=["knowledge"])


class SearchIn(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    categories: list[str] | None = None
    limit: int = Field(default=10, ge=1, le=30)


@router.post("/knowledge/search")
def search(body: SearchIn, c: Ctx = Depends(ctx), db: Session = Depends(get_db)):
    try:
        hits = retrieval.search(db, c.org_id, body.query, k=body.limit, categories=body.categories)
        mode = "hybrid"
    except LLMNotConfigured:
        # keyword search still works without an embedding provider
        hits = retrieval.search(db, c.org_id, body.query, k=body.limit, categories=body.categories, semantic=False)
        mode = "keyword"
    return {"mode": mode, "results": [h.citation() for h in hits]}


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: uuid.UUID | None = None


def msg_out(m: Message) -> dict:
    return {"id": str(m.id), "role": m.role, "content": m.content, "sources": m.sources, "meta": m.meta,
            "created_at": m.created_at}


@router.post("/chat")
def chat(body: ChatIn, c: Ctx = Depends(ctx), db: Session = Depends(get_db)):
    if body.conversation_id:
        conv = get_owned(db, Conversation, body.conversation_id, c)
        if conv.user_id != c.user.id:
            raise HTTPException(404, "Not found")
        history = [(m.role, m.content) for m in db.scalars(
            select(Message).where(Message.conversation_id == conv.id).order_by(Message.created_at))]
    else:
        conv = Conversation(org_id=c.org_id, user_id=c.user.id, title=body.message[:120])
        db.add(conv)
        db.flush()
        history = []
    user_msg = Message(org_id=c.org_id, conversation_id=conv.id, role="user", content=body.message)
    db.add(user_msg)

    run = Run(db, c.org_id, c.user.id, "qa", max_calls=2)
    try:
        out = qa.build(run).invoke({"question": body.message, "history": history})
    except Exception as e:
        db.rollback()
        # keep a failure record for operations dashboards even though the conversation turn is discarded
        db.add(WorkflowRun(org_id=c.org_id, user_id=c.user.id, kind="qa", status="failed", error=type(e).__name__))
        db.commit()
        if isinstance(e, LLMNotConfigured):
            raise HTTPException(503, str(e)) from None
        raise
    run.finish()
    r = out["result"]
    reply = Message(org_id=c.org_id, conversation_id=conv.id, role="assistant", content=r.answer,
                    sources=out["sources"], meta={"uncertain": out["uncertain"], "follow_ups": r.follow_ups,
                                                  "workflow_run_id": str(run.id)})
    db.add(reply)
    audit(db, c.org_id, c.user.id, "knowledge.question", conv, sources=len(out["sources"]))
    db.commit()
    return {"conversation_id": str(conv.id), "message": msg_out(reply)}


@router.get("/conversations")
def conversations(c: Ctx = Depends(ctx), db: Session = Depends(get_db)):
    rows = db.scalars(select(Conversation).where(Conversation.org_id == c.org_id, Conversation.user_id == c.user.id)
                      .order_by(Conversation.updated_at.desc()).limit(100)).all()
    return [{"id": str(x.id), "title": x.title, "updated_at": x.updated_at} for x in rows]


def _mine(db: Session, conv_id: uuid.UUID, c: Ctx) -> Conversation:
    conv = get_owned(db, Conversation, conv_id, c)
    if conv.user_id != c.user.id:  # conversations are private to their author
        raise HTTPException(404, "Not found")
    return conv


@router.get("/conversations/{conv_id}/messages")
def messages(conv_id: uuid.UUID, c: Ctx = Depends(ctx), db: Session = Depends(get_db)):
    conv = _mine(db, conv_id, c)
    return [msg_out(m) for m in db.scalars(select(Message).where(Message.conversation_id == conv.id)
                                           .order_by(Message.created_at))]


@router.delete("/conversations/{conv_id}", status_code=204)
def delete_conversation(conv_id: uuid.UUID, c: Ctx = Depends(ctx), db: Session = Depends(get_db)):
    db.delete(_mine(db, conv_id, c))
    db.commit()
