"""Background worker: `python -m app.worker`. Runs document ingestion, research and proposal generation."""

import logging
import time
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Document, Job, Prospect, Proposal, ProposalVersion, ResearchRun
from app.services import ingest, jobs
from app.services.extract import ExtractionError
from app.services.llm import BudgetExceeded, LLMNotConfigured, Run
from app.services.webfetch import FetchError
from app.workflows import proposal as proposal_wf
from app.workflows import research as research_wf

log = logging.getLogger("salespilot.worker")
# errors whose message is safe to show users and that retrying cannot fix
PERMANENT = (ExtractionError, LLMNotConfigured, BudgetExceeded, FetchError, ValueError)


def user_message(e: Exception, job: Job) -> str:
    return str(e) if isinstance(e, PERMANENT) else f"Unexpected error while processing (reference {job.id})."


def do_ingest(db: Session, job: Job) -> None:
    ingest.process_document(db, uuid.UUID(job.payload["document_id"]), int(job.payload["version"]))


def fail_ingest(db: Session, job: Job, msg: str) -> None:
    doc = db.get(Document, uuid.UUID(job.payload["document_id"]))
    if doc and doc.version == int(job.payload["version"]):
        doc.status, doc.error = "failed", msg


def do_research(db: Session, job: Job) -> None:
    rr = db.get(ResearchRun, uuid.UUID(job.payload["research_run_id"]))
    if rr.status == "done":
        return  # idempotent on retry
    prospect = db.get(Prospect, rr.prospect_id)
    rr.status, prospect.research_status = "running", "running"
    run = Run(db, rr.org_id, rr.user_id, "research")
    rr.workflow_run_id = run.id
    db.commit()
    try:
        research_wf.build(run, prospect, rr).invoke({})
        run.finish()
    except Exception as e:
        run.finish(user_message(e, job))
        db.commit()
        raise
    db.commit()


def fail_research(db: Session, job: Job, msg: str) -> None:
    rr = db.get(ResearchRun, uuid.UUID(job.payload["research_run_id"]))
    rr.status, rr.error = "failed", msg
    db.get(Prospect, rr.prospect_id).research_status = "failed"


def do_proposal(db: Session, job: Job) -> None:
    p = db.get(Proposal, uuid.UUID(job.payload["proposal_id"]))
    expected = int(job.payload["version"])
    if p.current_version >= expected:
        return  # this version was already produced (retry after a crash post-commit)
    section = job.payload.get("section") or None
    base = None
    if section:
        prev = db.scalar(select(ProposalVersion).where(ProposalVersion.proposal_id == p.id,
                                                       ProposalVersion.version == p.current_version))
        base = prev.sections
    run = Run(db, p.org_id, uuid.UUID(job.payload["user_id"]), "proposal")
    db.commit()
    try:
        inputs = proposal_wf.ProposalInputs(**p.inputs)
        out = proposal_wf.build(run, inputs, only=section, base_sections=base).invoke({})
        run.finish()
    except Exception as e:
        run.finish(user_message(e, job))
        db.commit()
        raise
    db.add(ProposalVersion(org_id=p.org_id, proposal_id=p.id, version=expected, sections=out["sections"],
                           pricing=out["pricing"], warnings=out["warnings"], created_by=run.user_id,
                           note=f"Regenerated '{section}'" if section else "AI draft"))
    p.current_version, p.status, p.error = expected, "draft", None
    db.commit()


def fail_proposal(db: Session, job: Job, msg: str) -> None:
    p = db.get(Proposal, uuid.UUID(job.payload["proposal_id"]))
    p.status = "draft" if p.current_version else "failed"
    p.error = msg


HANDLERS = {
    "ingest": (do_ingest, fail_ingest),
    "research": (do_research, fail_research),
    "proposal": (do_proposal, fail_proposal),
}


def run_one(db: Session) -> bool:
    job = jobs.claim(db)
    if job is None:
        return False
    do, fail = HANDLERS[job.kind]
    try:
        do(db, job)
        jobs.finish(db, job)
    except Exception as e:
        db.rollback()
        if isinstance(e, PERMANENT):
            job.attempts = job.max_attempts
        else:
            log.exception("job %s (%s) failed", job.id, job.kind)
        msg = user_message(e, job)
        if jobs.finish(db, job, msg):
            fail(db, job, msg)
            db.commit()
    return True


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    log.info("worker started")
    while True:
        with SessionLocal() as db:
            busy = run_one(db)
        if not busy:
            time.sleep(1)


if __name__ == "__main__":
    main()
