from fastapi import HTTPException
import pytest

from app.api import routes_cell


def test_cell_contract_verification_ingest_requires_admin_role(monkeypatch):
    monkeypatch.setattr(routes_cell, "_require_role", lambda *_args: (_ for _ in ()).throw(HTTPException(status_code=403, detail="forbidden")))

    with pytest.raises(HTTPException) as exc:
        routes_cell.cell_contract_verification_ingest(
            "dimy_docs",
            routes_cell.CellContractVerificationIngestRequest(
                cellType="CommonsTaxonomyCell",
                targetEndpoint="cell:///CommonsTaxonomy",
                verificationStatus="completed",
                chunks=[routes_cell.CellContractVerificationChunkIngest(id="summary", documentKind="summary", content="ok")],
            ),
            identity=routes_cell.CellIdentity(user_id="u1"),
        )
    assert exc.value.status_code == 403


def test_cell_contract_verification_ingest_rejects_source_type_outside_case(monkeypatch):
    monkeypatch.setattr(routes_cell, "_require_role", lambda *_args: "admin")
    monkeypatch.setattr(routes_cell, "_case_source_types", lambda _case_id: ["cellprotocol_docs"])

    with pytest.raises(HTTPException) as exc:
        routes_cell.cell_contract_verification_ingest(
            "dimy_docs",
            routes_cell.CellContractVerificationIngestRequest(
                cellType="CommonsTaxonomyCell",
                targetEndpoint="cell:///CommonsTaxonomy",
                verificationStatus="completed",
                sourceType="not-enabled",
                chunks=[routes_cell.CellContractVerificationChunkIngest(id="summary", documentKind="summary", content="ok")],
            ),
            identity=routes_cell.CellIdentity(user_id="u1"),
        )
    assert exc.value.status_code == 400
    assert "not enabled" in exc.value.detail


def test_cell_contract_verification_ingest_delegates_to_upsert(monkeypatch):
    monkeypatch.setattr(routes_cell, "_require_role", lambda *_args: "admin")
    monkeypatch.setattr(routes_cell, "_case_source_types", lambda _case_id: ["cellprotocol_docs", "haven_docs"])

    captured = {}

    def _fake_upsert(case_id: str, record: dict):
        captured["case_id"] = case_id
        captured["record"] = record
        return {
            "doc_id": "cell-contract-123",
            "title": "CommonsTaxonomyCell verification for cell:///CommonsTaxonomy",
            "source_type": "cellprotocol_docs",
            "chunk_count": 2,
        }

    monkeypatch.setattr(routes_cell, "upsert_contract_verification_record", _fake_upsert)

    resp = routes_cell.cell_contract_verification_ingest(
        "dimy_docs",
        routes_cell.CellContractVerificationIngestRequest(
            repo="CellProtocol",
            cellType="CommonsTaxonomyCell",
            targetEndpoint="cell:///CommonsTaxonomy",
            targetLabel="taxonomy",
            verificationStatus="failed",
            lastVerifiedAt="2026-03-14T12:00:00Z",
            failedAssertionCount=1,
            sourceType="cellprotocol_docs",
            recordMarkdown="# Verification",
            chunks=[
                routes_cell.CellContractVerificationChunkIngest(
                    id="summary",
                    documentKind="summary",
                    content="# Summary",
                ),
                routes_cell.CellContractVerificationChunkIngest(
                    id="failed",
                    documentKind="failed_assertion",
                    key="taxonomy.validate.purposeTree",
                    phase="flow.taxonomy.validate.completed",
                    status="failed",
                    content="Expected flow topic",
                ),
            ],
        ),
        identity=routes_cell.CellIdentity(user_id="u1"),
    )

    assert resp.case_id == "dimy_docs"
    assert resp.doc_id == "cell-contract-123"
    assert resp.chunk_count == 2
    assert captured["case_id"] == "dimy_docs"
    assert captured["record"]["cellType"] == "CommonsTaxonomyCell"
    assert captured["record"]["chunks"][1]["phase"] == "flow.taxonomy.validate.completed"
