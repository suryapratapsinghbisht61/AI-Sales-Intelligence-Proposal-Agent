"""Provider-agnostic model access. Every call goes through here so usage, budgets and limits are enforced once."""

import time
from datetime import UTC, datetime
from decimal import Decimal

from langchain.chat_models import init_chat_model
from langchain.embeddings import init_embeddings
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import ModelUsageEvent, Organization, WorkflowRun


class LLMNotConfigured(Exception):
    pass


class BudgetExceeded(Exception):
    pass


# Tests swap these for LangChain fakes; production leaves them None.
chat_override = None
embeddings_override = None
_cache: dict = {}


def chat_model(fast: bool = False):
    if chat_override is not None:
        return chat_override
    s = get_settings()
    name = (s.fast_model if fast else "") or s.chat_model
    if not name:
        raise LLMNotConfigured("No chat model configured. Set CHAT_MODEL (e.g. anthropic:claude-sonnet-5-5).")
    if name not in _cache:
        _cache[name] = init_chat_model(
            name, max_tokens=s.max_output_tokens, timeout=s.llm_timeout_s, max_retries=s.llm_max_retries
        )
    return _cache[name]


def model_name(fast: bool = False) -> str:
    s = get_settings()
    return "test" if chat_override is not None else ((s.fast_model if fast else "") or s.chat_model)


def embeddings():
    if embeddings_override is not None:
        return embeddings_override
    s = get_settings()
    if not s.embedding_model:
        raise LLMNotConfigured(
            "No embedding model configured. Set EMBEDDING_MODEL (e.g. openai:text-embedding-3-small)."
        )
    key = "emb:" + s.embedding_model
    if key not in _cache:
        # OpenAI models can shorten to the DB's fixed dimension; other providers must natively match it.
        kw = {"dimensions": s.embedding_dim} if s.embedding_model.startswith("openai:") else {}
        _cache[key] = init_embeddings(s.embedding_model, **kw)
    return _cache[key]


def embed_documents(texts: list[str]) -> list[list[float]]:
    vecs = embeddings().embed_documents(texts)
    _check_dim(vecs[0] if vecs else None)
    return vecs


def embed_query(text: str) -> list[float]:
    v = embeddings().embed_query(text)
    _check_dim(v)
    return v


def _check_dim(v) -> None:
    dim = get_settings().embedding_dim
    if v is not None and len(v) != dim:
        raise LLMNotConfigured(f"Embedding model returns {len(v)} dims but the database expects {dim}.")


class Run:
    """One tracked workflow execution: events, model-call limit, usage and token budget."""

    def __init__(self, db: Session, org_id, user_id, kind: str, max_calls: int = 12):
        self.db, self.org_id, self.user_id, self.max_calls, self.calls = db, org_id, user_id, max_calls, 0
        self.started = time.monotonic()
        self.wf = WorkflowRun(org_id=org_id, user_id=user_id, kind=kind, events=[])
        db.add(self.wf)
        db.flush()

    @property
    def id(self):
        return self.wf.id

    def event(self, name: str, **data) -> None:
        self.wf.events = [*self.wf.events, {"at": datetime.now(UTC).isoformat(), "step": name, **data}]

    def finish(self, error: str | None = None) -> None:
        self.wf.status = "failed" if error else "succeeded"
        self.wf.error = error
        self.wf.duration_ms = int((time.monotonic() - self.started) * 1000)

    def _check_budget(self) -> None:
        self.calls += 1
        if self.calls > self.max_calls:
            raise BudgetExceeded("This workflow hit its model-call limit.")
        org = self.db.get(Organization, self.org_id)
        budget = org.monthly_token_budget or get_settings().org_monthly_token_budget
        month_start = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        used = self.db.scalar(
            select(func.coalesce(func.sum(ModelUsageEvent.input_tokens + ModelUsageEvent.output_tokens), 0)).where(
                ModelUsageEvent.org_id == self.org_id, ModelUsageEvent.created_at >= month_start
            )
        )
        if used >= budget:
            raise BudgetExceeded("Your organization's monthly AI token budget is used up.")

    def _record(self, purpose: str, fast: bool, msg) -> None:
        u = getattr(msg, "usage_metadata", None) or {}
        name = model_name(fast)
        tin, tout = u.get("input_tokens", 0), u.get("output_tokens", 0)
        price = get_settings().prices.get(name)
        cost = Decimal(str((tin * price[0] + tout * price[1]) / 1_000_000)) if price else None
        self.db.add(
            ModelUsageEvent(
                org_id=self.org_id,
                user_id=self.user_id,
                workflow_run_id=self.wf.id,
                model=name,
                purpose=purpose,
                input_tokens=tin,
                output_tokens=tout,
                est_cost_usd=cost,
            )
        )

    def structured[T: BaseModel](self, schema: type[T], messages: list, purpose: str, fast: bool = False) -> T:
        """Model call whose output is validated against a Pydantic schema; raises on invalid output."""
        self._check_budget()
        out = chat_model(fast).with_structured_output(schema, include_raw=True).invoke(messages)
        self._record(purpose, fast, out["raw"])
        if out.get("parsing_error") or out.get("parsed") is None:
            raise ValueError(f"Model returned output that failed validation for {schema.__name__}")
        self.event("model_call", purpose=purpose)
        return out["parsed"]
