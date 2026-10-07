from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


REQUIRED_PATHS = [
    "/health",
    "/v1/query",
    "/v1/retrieve",
    "/v1/cases",
    "/v1/cases/{case_id}/status",
    "/v1/cases/{case_id}/retrieve",
    "/v1/cell/cases",
    "/v1/cell/cases/{case_id}/query",
    "/v1/cell/cases/{case_id}/retrieve",
    "/v1/cell/cases/{case_id}/status",
    "/v1/research/cases",
    "/v1/research/query",
    "/v1/research/retrieve",
    "/v1/research/cases/{case_id}/status",
    "/v1/admin/case-prompt-profiles",
    "/v1/admin/catalog/publish",
    "/v1/admin/catalog/reindex",
    "/v1/admin/catalog/status",
    "/v1/admin/media/publish",
    "/v1/admin/media/status",
]


@dataclass
class CheckResult:
    base_url: str
    ok: bool
    failures: list[str]
    details: dict[str, Any]


def _url(base_url: str, path: str) -> str:
    return base_url.rstrip("/") + path


def _get_json(url: str, timeout: float) -> tuple[int, Any]:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = response.read()
            status = int(response.status)
    except urllib.error.HTTPError as exc:
        data = exc.read()
        status = int(exc.code)
    except urllib.error.URLError as exc:
        return 0, f"request failed: {exc.reason}"
    if not data:
        return status, None
    try:
        return status, json.loads(data.decode("utf-8"))
    except Exception:
        return status, data.decode("utf-8", errors="replace")


def check_base_url(base_url: str, timeout: float) -> CheckResult:
    failures: list[str] = []
    details: dict[str, Any] = {}

    health_status, health_payload = _get_json(_url(base_url, "/health"), timeout)
    details["health"] = {"status": health_status, "payload": health_payload}
    if health_status != 200 or not isinstance(health_payload, dict) or health_payload.get("ok") is not True:
        failures.append(f"/health returned {health_status}: {health_payload}")

    openapi_status, openapi_payload = _get_json(_url(base_url, "/openapi.json"), timeout)
    details["openapi_status"] = openapi_status
    if openapi_status != 200 or not isinstance(openapi_payload, dict):
        failures.append(f"/openapi.json returned {openapi_status}")
        details["paths"] = []
    else:
        paths = sorted((openapi_payload.get("paths") or {}).keys())
        details["paths"] = paths
        missing = [path for path in REQUIRED_PATHS if path not in set(paths)]
        if missing:
            failures.append("Missing OpenAPI paths: " + ", ".join(missing))

    return CheckResult(base_url=base_url, ok=not failures, failures=failures, details=details)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check deployed rag_service route/runtime contract.")
    parser.add_argument("base_urls", nargs="+", help="Base URL(s), for example http://127.0.0.1:8102")
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    results = [check_base_url(base_url, args.timeout) for base_url in args.base_urls]
    payload = {
        "ok": all(result.ok for result in results),
        "results": [
            {
                "base_url": result.base_url,
                "ok": result.ok,
                "failures": result.failures,
                "details": result.details,
            }
            for result in results
        ],
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for result in results:
            status = "ok" if result.ok else "FAILED"
            print(f"{result.base_url}: {status}")
            for failure in result.failures:
                print(f"  - {failure}")

    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
