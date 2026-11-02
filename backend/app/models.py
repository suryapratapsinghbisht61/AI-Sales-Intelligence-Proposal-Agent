import uuid
from datetime import datetime
from decimal import Decimal

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.config import get_settings
from app.db import Base

ROLES = ("owner", "admin", "sales_manager", "sales_rep")


class Common:
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


def org_fk() -> Mapped[uuid.UUID]:
    return mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)


# --- identity & tenancy -------------------------------------------------------


class User(Common, Base):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(320), unique=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    password_hash: Mapped[str] = mapped_column(String(200))
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UserSession(Common, Base):
    __tablename__ = "sessions"
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    active_org_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PasswordReset(Common, Base):
    __tablename__ = "password_resets"
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Organization(Common, Base):
    __tablename__ = "organizations"
    name: Mapped[str] = mapped_column(String(200))
    website: Mapped[str] = mapped_column(String(500), default="")
    industry: Mapped[str] = mapped_column(String(200), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    offerings: Mapped[str] = mapped_column(Text, default="")
    target_customer: Mapped[str] = mapped_column(Text, default="")
    target_markets: Mapped[str] = mapped_column(Text, default="")
    team_size: Mapped[int | None] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    onboarding_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    monthly_token_budget: Mapped[int | None] = mapped_column(Integer)


class Membership(Common, Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("org_id", "user_id"),)
    org_id: Mapped[uuid.UUID] = org_fk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20))


class Invitation(Common, Base):
    __tablename__ = "invitations"
    org_id: Mapped[uuid.UUID] = org_fk()
    email: Mapped[str] = mapped_column(String(320))
    role: Mapped[str] = mapped_column(String(20))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    invited_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# --- knowledge base -----------------------------------------------------------


class Document(Common, Base):
    __tablename__ = "documents"
    org_id: Mapped[uuid.UUID] = org_fk()
    title: Mapped[str] = mapped_column(String(300))
    filename: Mapped[str] = mapped_column(String(300))
    content_type: Mapped[str] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(String(500))
    category: Mapped[str] = mapped_column(String(40), default="other")
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="uploaded")  # uploaded|processing|ready|failed
    error: Mapped[str | None] = mapped_column(Text)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    text_preview: Mapped[str] = mapped_column(Text, default="")
    uploaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "version", "ordinal"),
        Index("ix_chunks_tsv", "tsv", postgresql_using="gin"),
        Index(
            "ix_chunks_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = org_fk()
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    ordinal: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    page: Mapped[int | None] = mapped_column(Integer)
    section: Mapped[str | None] = mapped_column(String(300))
    embedding = mapped_column(Vector(get_settings().embedding_dim))
    tsv = mapped_column(TSVECTOR, Computed("to_tsvector('english', content)", persisted=True))


class Job(Common, Base):
    """Postgres-backed durable queue; workers claim rows with FOR UPDATE SKIP LOCKED."""

    __tablename__ = "jobs"
    __table_args__ = (Index("ix_jobs_claim", "status", "run_after"),)
    org_id: Mapped[uuid.UUID] = org_fk()
    kind: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued|running|done|failed
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)


# --- AI workspace -------------------------------------------------------------


class Conversation(Common, Base):
    __tablename__ = "conversations"
    org_id: Mapped[uuid.UUID] = org_fk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(300))


class Message(Common, Base):
    __tablename__ = "messages"
    org_id: Mapped[uuid.UUID] = org_fk()
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(20))  # user|assistant
    content: Mapped[str] = mapped_column(Text)
    # [{chunk_id, document_id, title, page, section, excerpt}] — only chunks actually retrieved
    sources: Mapped[list] = mapped_column(JSONB, default=list)
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)


class WorkflowRun(Common, Base):
    __tablename__ = "workflow_runs"
    org_id: Mapped[uuid.UUID] = org_fk()
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(40))  # qa|research|proposal|ingest
    status: Mapped[str] = mapped_column(String(20), default="running")  # running|succeeded|failed
    events: Mapped[list] = mapped_column(JSONB, default=list)
    error: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[int | None] = mapped_column(Integer)


class ModelUsageEvent(Common, Base):
    __tablename__ = "model_usage_events"
    org_id: Mapped[uuid.UUID] = org_fk()
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    workflow_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("workflow_runs.id", ondelete="SET NULL"))
    model: Mapped[str] = mapped_column(String(200))
    purpose: Mapped[str] = mapped_column(String(40))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    est_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))


# --- sales --------------------------------------------------------------------


class Prospect(Common, Base):
    __tablename__ = "prospects"
    __table_args__ = (
        Index("uq_prospect_domain", "org_id", "domain", unique=True, postgresql_where=text("domain <> ''")),
    )
    org_id: Mapped[uuid.UUID] = org_fk()
    name: Mapped[str] = mapped_column(String(300))
    domain: Mapped[str] = mapped_column(String(300), default="")
    industry: Mapped[str] = mapped_column(String(200), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    location: Mapped[str] = mapped_column(String(200), default="")
    company_size: Mapped[str] = mapped_column(String(100), default="")
    contact_name: Mapped[str] = mapped_column(String(200), default="")
    contact_email: Mapped[str] = mapped_column(String(320), default="")
    source_url: Mapped[str] = mapped_column(String(1000), default="")
    research_status: Mapped[str] = mapped_column(String(20), default="new")  # new|queued|running|done|failed
    score: Mapped[int | None] = mapped_column(Integer)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    notes: Mapped[str] = mapped_column(Text, default="")
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    last_researched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    latest_research_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class QualificationRubric(Common, Base):
    __tablename__ = "qualification_rubrics"
    __table_args__ = (UniqueConstraint("org_id", "version"),)
    org_id: Mapped[uuid.UUID] = org_fk()
    version: Mapped[int] = mapped_column(Integer)
    criteria: Mapped[list] = mapped_column(JSONB)  # [{key, label, description, weight}]
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class ResearchRun(Common, Base):
    __tablename__ = "research_runs"
    org_id: Mapped[uuid.UUID] = org_fk()
    prospect_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("prospects.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(20), default="queued")
    inputs: Mapped[dict] = mapped_column(JSONB, default=dict)
    facts: Mapped[list] = mapped_column(JSONB, default=list)  # [{claim, kind, source_url, quote}]
    needs: Mapped[list] = mapped_column(JSONB, default=list)  # hypotheses, always labelled as such
    unknowns: Mapped[list] = mapped_column(JSONB, default=list)
    qualification: Mapped[dict] = mapped_column(JSONB, default=dict)
    score: Mapped[int | None] = mapped_column(Integer)
    rubric_version: Mapped[int | None] = mapped_column(Integer)
    recommended_offering: Mapped[str] = mapped_column(Text, default="")
    value_proposition: Mapped[str] = mapped_column(Text, default="")
    warnings: Mapped[list] = mapped_column(JSONB, default=list)
    error: Mapped[str | None] = mapped_column(Text)
    workflow_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class ProspectSource(Common, Base):
    __tablename__ = "prospect_sources"
    org_id: Mapped[uuid.UUID] = org_fk()
    prospect_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("prospects.id", ondelete="CASCADE"), index=True)
    research_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("research_runs.id", ondelete="CASCADE"))
    url: Mapped[str] = mapped_column(String(1000))
    title: Mapped[str] = mapped_column(String(500), default="")
    content: Mapped[str] = mapped_column(Text, default="")  # extracted text, capped; used to verify quotes
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OutreachDraft(Common, Base):
    __tablename__ = "outreach_drafts"
    org_id: Mapped[uuid.UUID] = org_fk()
    prospect_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("prospects.id", ondelete="CASCADE"), index=True)
    research_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("research_runs.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(40), default="cold_email")
    subject: Mapped[str] = mapped_column(String(300), default="")
    body: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft|sent
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


# --- proposals ----------------------------------------------------------------


class PriceItem(Common, Base):
    """Approved price list. Proposals may only price from these rows."""

    __tablename__ = "price_items"
    org_id: Mapped[uuid.UUID] = org_fk()
    name: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    unit: Mapped[str] = mapped_column(String(60), default="unit")
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Proposal(Common, Base):
    __tablename__ = "proposals"
    org_id: Mapped[uuid.UUID] = org_fk()
    prospect_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("prospects.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    # generating|draft|pending_approval|changes_requested|approved|rejected|failed
    status: Mapped[str] = mapped_column(String(30), default="generating")
    current_version: Mapped[int] = mapped_column(Integer, default=0)
    inputs: Mapped[dict] = mapped_column(JSONB, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class ProposalVersion(Common, Base):
    __tablename__ = "proposal_versions"
    __table_args__ = (UniqueConstraint("proposal_id", "version"),)
    org_id: Mapped[uuid.UUID] = org_fk()
    proposal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proposals.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    sections: Mapped[list] = mapped_column(JSONB)  # [{key, title, content, sources, flags}]
    pricing: Mapped[dict] = mapped_column(JSONB, default=dict)  # computed deterministically
    warnings: Mapped[list] = mapped_column(JSONB, default=list)
    note: Mapped[str] = mapped_column(String(300), default="")
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


# --- operations ---------------------------------------------------------------


class ApprovalRequest(Common, Base):
    __tablename__ = "approval_requests"
    __table_args__ = (
        # at most one open request per target
        Index(
            "uq_open_approval", "target_type", "target_id", unique=True, postgresql_where=text("status = 'pending'")
        ),
    )
    org_id: Mapped[uuid.UUID] = org_fk()
    kind: Mapped[str] = mapped_column(String(40))  # proposal
    target_type: Mapped[str] = mapped_column(String(40))
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    target_version: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|approved|rejected|changes_requested
    summary: Mapped[dict] = mapped_column(JSONB, default=dict)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    decided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    comment: Mapped[str] = mapped_column(Text, default="")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    org_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(80))
    target_type: Mapped[str] = mapped_column(String(40), default="")
    target_id: Mapped[str] = mapped_column(String(64), default="")
    detail: Mapped[dict] = mapped_column(JSONB, default=dict)
