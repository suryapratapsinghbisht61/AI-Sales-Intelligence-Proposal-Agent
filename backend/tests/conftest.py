import os
import uuid

os.environ["DATABASE_URL"] = "postgresql+psycopg://salespilot:salespilot@localhost:5432/salespilot_test"
os.environ["STORAGE_DIR"] = "/tmp/salespilot-test-uploads"
os.environ["RATE_LIMIT_PER_MINUTE"] = "100000"
os.environ["CHAT_MODEL"] = os.environ["EMBEDDING_MODEL"] = ""

import pytest  # noqa: E402
from langchain_core.embeddings import DeterministicFakeEmbedding  # noqa: E402
from langchain_core.messages import AIMessage  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

admin = create_engine("postgresql+psycopg://salespilot:salespilot@localhost:5432/salespilot",
                      isolation_level="AUTOCOMMIT")
with admin.connect() as c:
    c.execute(text("DROP DATABASE IF EXISTS salespilot_test WITH (FORCE)"))
    c.execute(text("CREATE DATABASE salespilot_test"))

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402

command.upgrade(Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini")), "head")

from fastapi.testclient import TestClient  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.services import llm  # noqa: E402


class FakeChat:
    """Stands in for a chat model: `responders[SchemaName](messages)` builds the structured result."""

    def __init__(self):
        self.responders = {}

    def with_structured_output(self, schema, include_raw=True):
        outer = self

        class Bound:
            def invoke(self, messages):
                parsed = outer.responders[schema.__name__](messages)
                return {"raw": AIMessage("", usage_metadata={"input_tokens": 10, "output_tokens": 5,
                                                              "total_tokens": 15}), "parsed": parsed}
        return Bound()


@pytest.fixture(autouse=True)
def fake_models():
    fake = FakeChat()
    llm.chat_override, llm.embeddings_override = fake, DeterministicFakeEmbedding(size=768)
    yield fake
    llm.chat_override = llm.embeddings_override = None


@pytest.fixture
def db():
    with SessionLocal() as s:
        yield s


def make_user(org_name: str | None = "Acme", role: str = "owner"):
    """Signed-in client; creates an org (as owner) unless org_name is None."""
    c = TestClient(app)
    email = f"u{uuid.uuid4().hex[:8]}@example.com"
    assert c.post("/api/v1/auth/signup", json={"email": email, "password": "correct horse battery"}).status_code == 201
    c.email = email
    if org_name:
        r = c.post("/api/v1/organizations", json={"name": org_name, "offerings": "Cloud migration services"})
        assert r.status_code == 201, r.text
        c.org_id = r.json()["id"]
    return c


def add_member(owner: TestClient, role: str) -> TestClient:
    m = make_user(None)
    link = owner.post("/api/v1/invitations", json={"email": m.email, "role": role}).json()["link"]
    assert m.post("/api/v1/invitations/accept", json={"token": link.split("token=")[1]}).status_code == 200
    return m


def work(db):
    from app.worker import run_one
    while run_one(db):
        pass
