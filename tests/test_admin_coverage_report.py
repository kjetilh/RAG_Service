from app.api import routes_admin


def test_admin_coverage_report_returns_helper_payload(monkeypatch):
    monkeypatch.setattr(
        routes_admin,
        "build_coverage_report",
        lambda: {"summary": {"total_documents": 3}, "recommendations": []},
    )
    resp = routes_admin.admin_coverage_report()
    assert resp["ok"] is True
    assert resp["report"]["summary"]["total_documents"] == 3
