from app.api import routes_admin


def test_admin_coverage_actions_returns_helper_payload(monkeypatch):
    monkeypatch.setattr(
        routes_admin,
        "build_coverage_report",
        lambda: {"summary": {"total_documents": 3, "total_chunks": 9}},
    )
    monkeypatch.setattr(
        routes_admin,
        "build_coverage_actions",
        lambda report: {"summary": report["summary"], "actions": [{"id": "router_tuning"}]},
    )
    resp = routes_admin.admin_coverage_actions()
    assert resp["ok"] is True
    assert resp["report_summary"]["total_documents"] == 3
    assert resp["actions"]["actions"][0]["id"] == "router_tuning"
