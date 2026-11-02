import re

from conftest import add_member, make_user, work

from app.services import webfetch
from app.workflows.proposal import Draft, SectionDraft
from app.workflows.qa import Answer
from app.workflows.research import CriterionRating, Extraction, Fact, Outreach

MD = b"# Implementation process\nOur implementation takes six weeks: discovery, migration, and hypercare.\n" \
     b"# Pricing\nThe enterprise plan is approved at 4000 USD per month."


def upload(c, content=MD, name="process.md", category="product_docs"):
    return c.post("/api/v1/documents", files={"file": (name, content, "text/markdown")},
                  data={"category": category})


def ids_in(messages):
    return re.findall(r'<document id="([^"]+)"', messages[-1].content)


def test_auth_flow():
    c = make_user()
    me = c.get("/api/v1/me").json()
    assert me["active_organization"]["role"] == "owner" and "approvals.decide" in me["permissions"]
    assert c.post("/api/v1/auth/login", json={"email": c.email, "password": "wrong password!!"}).status_code == 401
    assert c.post("/api/v1/auth/logout").status_code == 200
    assert c.get("/api/v1/me").status_code == 401
    assert c.post("/api/v1/auth/login", json={"email": c.email, "password": "correct horse battery"}).status_code == 200
    assert c.get("/api/v1/me").json()["active_organization"] is not None


def test_cross_origin_post_blocked():
    c = make_user()
    r = c.post("/api/v1/prospects", json={"name": "X"}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403


def test_upload_validation():
    c = make_user()
    assert c.post("/api/v1/documents", files={"file": ("x.exe", b"MZ", "application/octet-stream")}).status_code == 415
    assert c.post("/api/v1/documents", files={"file": ("x.pdf", b"not a pdf", "application/pdf")}).status_code == 415
    assert upload(c).status_code == 201
    assert upload(c).status_code == 409  # duplicate content


def test_ingest_search_replace(db):
    c = make_user()
    doc = upload(c).json()
    work(db)
    d = c.get(f"/api/v1/documents/{doc['id']}").json()
    assert d["status"] == "ready" and d["chunk_count"] >= 1
    hits = c.post("/api/v1/knowledge/search", json={"query": "implementation six weeks"}).json()["results"]
    assert hits and hits[0]["document_id"] == doc["id"]
    r = c.post(f"/api/v1/documents/{doc['id']}/replace",
               files={"file": ("process.md", b"# New\nOnboarding is handled by partners.", "text/markdown")})
    assert r.json()["version"] == 2
    work(db)
    hits = c.post("/api/v1/knowledge/search", json={"query": "implementation six weeks hypercare"}).json()["results"]
    assert all("six weeks" not in h["excerpt"] for h in hits)


def test_failed_ingest_is_visible_and_retryable(db, fake_models):
    from app.services import llm
    c = make_user()
    llm.embeddings_override = None  # no embedding provider configured -> permanent, explained failure
    doc = upload(c).json()
    work(db)
    d = c.get(f"/api/v1/documents/{doc['id']}").json()
    assert d["status"] == "failed" and "EMBEDDING_MODEL" in d["error"]
    assert c.post(f"/api/v1/documents/{doc['id']}/retry").json()["status"] == "uploaded"


def test_chat_citations_are_validated(db, fake_models):
    c = make_user()
    upload(c)
    work(db)
    fake_models.responders["Answer"] = lambda m: Answer(answer="Six weeks.", cited_ids=[ids_in(m)[0], "invented-id"])
    r = c.post("/api/v1/chat", json={"message": "How long does implementation take?"}).json()
    srcs = r["message"]["sources"]
    assert len(srcs) == 1 and srcs[0]["title"] == "process.md" and r["message"]["meta"]["uncertain"] is False
    msgs = c.get(f"/api/v1/conversations/{r['conversation_id']}/messages").json()
    assert [m["role"] for m in msgs] == ["user", "assistant"]


def test_chat_without_evidence_is_uncertain():
    c = make_user()  # empty knowledge base: the model must not even be called
    r = c.post("/api/v1/chat", json={"message": "What is our refund policy?"}).json()
    assert r["message"]["meta"]["uncertain"] is True and r["message"]["sources"] == []


def test_chat_terse_uncertain_answer_is_replaced(db, fake_models):
    c = make_user()
    upload(c)
    work(db)
    fake_models.responders["Answer"] = lambda m: Answer(answer="insufficient_evidence", insufficient_evidence=True)
    m = c.post("/api/v1/chat", json={"message": "implementation refund"}).json()["message"]
    assert m["meta"]["uncertain"] and "couldn't find" in m["content"]


def test_chat_unconfigured_model_is_503(db):
    from app.services import llm
    c = make_user()
    upload(c)
    work(db)
    llm.chat_override = None
    r = c.post("/api/v1/chat", json={"message": "implementation"})
    assert r.status_code == 503 and "CHAT_MODEL" in r.json()["detail"]


def test_cross_tenant_isolation(db, fake_models):
    a, b = make_user("A Corp"), make_user("B Corp")
    doc = upload(a).json()
    work(db)
    prospect = a.post("/api/v1/prospects", json={"name": "Globex", "domain": "globex.example"}).json()
    fake_models.responders["Answer"] = lambda m: Answer(answer="x", cited_ids=ids_in(m))
    conv = a.post("/api/v1/chat", json={"message": "implementation"}).json()["conversation_id"]
    for path in (f"/api/v1/documents/{doc['id']}", f"/api/v1/documents/{doc['id']}/download",
                 f"/api/v1/prospects/{prospect['id']}", f"/api/v1/conversations/{conv}/messages"):
        assert b.get(path).status_code == 404, path
    assert b.delete(f"/api/v1/documents/{doc['id']}").status_code == 404
    assert b.patch(f"/api/v1/prospects/{prospect['id']}", json={"name": "pwned"}).status_code == 404
    assert b.post("/api/v1/knowledge/search", json={"query": "implementation six weeks"}).json()["results"] == []
    assert b.get("/api/v1/prospects").json()["total"] == 0
    assert b.get("/api/v1/activity").json() == [] or all(x["target_id"] != doc["id"] for x in b.get("/api/v1/activity").json())
    # B's chat never sees A's chunks
    r = b.post("/api/v1/chat", json={"message": "implementation six weeks"}).json()
    assert r["message"]["sources"] == []
    # cannot switch into an org you don't belong to
    assert b.post("/api/v1/session/organization", json={"organization_id": a.org_id}).status_code == 404


def test_prospect_duplicates_and_csv(db):
    c = make_user()
    assert c.post("/api/v1/prospects", json={"name": "Initech", "domain": "https://www.initech.example/"}).json()[
        "domain"] == "initech.example"
    assert c.post("/api/v1/prospects", json={"name": "Other", "domain": "initech.example"}).status_code == 409
    csv_data = b"name,domain,industry\nInitech,initech.example,IT\nHooli,hooli.example,=cmd()\n"
    r = c.post("/api/v1/prospects/import", files={"file": ("p.csv", csv_data, "text/csv")}).json()
    assert r["created"] == 1 and len(r["skipped_duplicates"]) == 1
    out = c.get("/api/v1/prospects/export").text
    assert "'=cmd()" in out  # formula injection neutralised


def test_research_verifies_quotes(db, fake_models, monkeypatch):
    c = make_user()
    page = webfetch.Page(url="https://globex.example/about", title="About",
                         text="Globex is a regional hospital network. We are moving our data centers to the cloud in 2026.")
    monkeypatch.setattr(webfetch, "fetch_site", lambda d: [page])
    fake_models.responders["Extraction"] = lambda m: Extraction(
        summary="Hospital network.", industry="Healthcare",
        facts=[Fact(claim="Moving data centers to cloud", quote="moving our data centers to the cloud",
                    source_url=page.url),
               Fact(claim="Revenue is $2B", quote="revenue of two billion dollars", source_url=page.url),
               Fact(claim="Invented source", quote="whatever text here", source_url="https://elsewhere.example")],
        ratings=[CriterionRating(key="evidence_of_need", rating="strong", evidence_quote="moving our data centers to the cloud",
                                 source_url=page.url, explanation="Cloud move"),
                 CriterionRating(key="industry_fit", rating="strong", evidence_quote="they love our product a lot",
                                 source_url=page.url, explanation="made up")],
        recommended_offering="Cloud migration")
    fake_models.responders["Outreach"] = lambda m: Outreach(subject="Cloud move", body="Hi", rationale="cloud fact")
    p = c.post("/api/v1/prospects", json={"name": "Globex", "domain": "globex.example"}).json()
    assert c.post(f"/api/v1/prospects/{p['id']}/research", json={}).status_code == 202
    work(db)
    d = c.get(f"/api/v1/prospects/{p['id']}").json()
    r = d["research"]
    assert r["status"] == "done", r
    kinds = {f["claim"]: f["kind"] for f in r["facts"]}
    assert kinds == {"Moving data centers to cloud": "verified", "Revenue is $2B": "sourced_unverified"}
    crit = {x["key"]: x["rating"] for x in r["qualification"]["criteria"]}
    assert crit["evidence_of_need"] == "strong" and crit["industry_fit"] == "unknown"
    assert r["score"] == 20 and r["rubric_version"] == 1  # only evidence_of_need (weight 20 of 100) counts
    assert r["sources"][0]["url"] == page.url and d["drafts"][0]["subject"] == "Cloud move"
    # cached on the next request
    assert c.post(f"/api/v1/prospects/{p['id']}/research", json={}).json()["cached"] is True


def _proposal(c, db, fake_models):
    price = c.post("/api/v1/price-items", json={"name": "Migration sprint", "unit": "sprint",
                                                "unit_price": "12500.00", "currency": "USD"}).json()
    upload(c)
    work(db)
    p = c.post("/api/v1/prospects", json={"name": "Globex"}).json()
    fake_models.responders["Draft"] = lambda m: Draft(sections=[
        SectionDraft(key="executive_summary", content="We guarantee success for $99,000.", source_ids=ids_in(m)[:1]),
        SectionDraft(key="solution", content="Six week implementation.", source_ids=["made-up"])])
    r = c.post("/api/v1/proposals", json={"prospect_id": p["id"], "title": "Globex migration",
                                          "price_lines": [{"price_item_id": price["id"], "quantity": 3}]})
    assert r.status_code == 202, r.text
    work(db)
    return c.get(f"/api/v1/proposals/{r.json()['id']}").json()


def test_proposal_pricing_and_validation(db, fake_models):
    c = make_user()
    prop = _proposal(c, db, fake_models)
    v = prop["version"]
    assert prop["status"] == "draft" and v["pricing"]["total"] == "37500.00"
    secs = {s["key"]: s for s in v["sections"]}
    assert "37500.00" in secs["pricing"]["content"] and secs["pricing"]["flags"] == [] or \
        secs["pricing"]["flags"] == ["Contains placeholders for missing information"]
    flags = secs["executive_summary"]["flags"]
    assert any("$99,000" in f for f in flags) and any("guarantee" in f for f in flags)
    assert len(secs["executive_summary"]["sources"]) == 1 and secs["solution"]["sources"] == []
    assert secs["case_studies"]["content"] == "[Not generated]"
    # manual edit -> new version, stale edits rejected
    e = c.patch(f"/api/v1/proposals/{prop['id']}", json={"base_version": 1, "sections": [
        {"key": "executive_summary", "content": "A careful, phased migration."}]}).json()
    assert e["current_version"] == 2 and e["version"]["sections"][0]["flags"] == []
    assert c.patch(f"/api/v1/proposals/{prop['id']}", json={"base_version": 1, "sections": []}).status_code == 409
    assert len(c.get(f"/api/v1/proposals/{prop['id']}/versions").json()) == 2
    assert c.post(f"/api/v1/proposals/{prop['id']}/export").status_code == 200


def test_proposal_rejects_foreign_price_item(db, fake_models):
    a, b = make_user(), make_user()
    price = a.post("/api/v1/price-items", json={"name": "X", "unit_price": "1", "currency": "USD"}).json()
    p = b.post("/api/v1/prospects", json={"name": "Y"}).json()
    r = b.post("/api/v1/proposals", json={"prospect_id": p["id"], "title": "t",
                                          "price_lines": [{"price_item_id": price["id"], "quantity": 1}]})
    assert r.status_code == 422


def test_approval_permissions(db, fake_models):
    owner = make_user()
    rep, manager = add_member(owner, "sales_rep"), add_member(owner, "sales_manager")
    assert rep.post("/api/v1/price-items", json={"name": "X", "unit_price": "1", "currency": "USD"}).status_code == 403
    prop = _proposal(owner, db, fake_models)
    aid = manager.post(f"/api/v1/proposals/{prop['id']}/submit").json()["approval_id"]
    assert manager.post(f"/api/v1/proposals/{prop['id']}/submit").status_code == 409  # already pending
    assert rep.post(f"/api/v1/approvals/{aid}/approve", json={}).status_code == 403
    assert manager.post(f"/api/v1/approvals/{aid}/approve", json={}).status_code == 403  # own request
    assert owner.patch(f"/api/v1/proposals/{prop['id']}", json={"base_version": 1, "sections": []}).status_code == 409
    r = owner.post(f"/api/v1/approvals/{aid}/approve", json={})
    assert r.status_code == 200 and r.json()["status"] == "approved"
    assert owner.post(f"/api/v1/approvals/{aid}/reject", json={"comment": "x"}).status_code == 409  # replay
    assert owner.get(f"/api/v1/proposals/{prop['id']}").json()["status"] == "approved"
    o = owner.get("/api/v1/analytics/overview").json()
    assert o["proposals_generated"] == 1 and o["documents_indexed"] == 1 and o["tokens_in"] > 0
