from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


def _base_url(raw: str) -> str:
    return raw.rstrip("/")


def _request_json(
    *,
    base_url: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    token: str | None = None,
    cell_secret: str | None = None,
    cell_user_id: str | None = None,
    timeout: float = 30.0,
) -> tuple[int, Any]:
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if cell_secret:
        headers["X-Cell-Gateway-Secret"] = cell_secret
    if cell_user_id:
        headers["X-Cell-User-Id"] = cell_user_id

    req = urllib.request.Request(
        _base_url(base_url) + path,
        data=body,
        headers=headers,
        method=method.upper(),
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = response.read()
            status = int(response.status)
    except urllib.error.HTTPError as exc:
        data = exc.read()
        status = int(exc.code)

    if not data:
        return status, None
    try:
        return status, json.loads(data.decode("utf-8"))
    except Exception:
        return status, data.decode("utf-8", errors="replace")


def _print(status: int, payload: Any) -> int:
    print(json.dumps({"status": status, "payload": payload}, ensure_ascii=False, indent=2))
    return 0 if 200 <= status < 300 else 1


def _path_part(value: str) -> str:
    return urllib.parse.quote(value, safe="")


def cmd_list_cases(args: argparse.Namespace) -> int:
    if args.token:
        path = "/v1/research/cases"
    elif args.cell_secret or args.cell_user_id:
        path = "/v1/cell/cases"
    else:
        path = "/v1/cases"
    status, payload = _request_json(
        base_url=args.base_url,
        method="GET",
        path=path,
        token=args.token,
        cell_secret=args.cell_secret,
        cell_user_id=args.cell_user_id,
        timeout=args.timeout,
    )
    return _print(status, payload)


def cmd_status(args: argparse.Namespace) -> int:
    case_id = _path_part(args.case_id)
    if args.token:
        path = f"/v1/research/cases/{case_id}/status"
    elif args.cell_secret or args.cell_user_id:
        path = f"/v1/cell/cases/{case_id}/status"
    else:
        path = f"/v1/cases/{case_id}/status"
    status, payload = _request_json(
        base_url=args.base_url,
        method="GET",
        path=path,
        token=args.token,
        cell_secret=args.cell_secret,
        cell_user_id=args.cell_user_id,
        timeout=args.timeout,
    )
    return _print(status, payload)


def _query_payload(args: argparse.Namespace) -> dict[str, Any]:
    payload: dict[str, Any] = {"query": args.query}
    if args.top_k is not None:
        payload["top_k"] = args.top_k
    if args.model_profile:
        payload["model_profile"] = args.model_profile
    if args.prompt_profile_case_id:
        payload["prompt_profile_case_id"] = args.prompt_profile_case_id
    if args.filters:
        payload["filters"] = json.loads(args.filters)
    return payload


def cmd_query(args: argparse.Namespace) -> int:
    payload = _query_payload(args)
    if args.token:
        payload["case_id"] = args.case_id
        path = "/v1/research/query"
    elif args.cell_secret or args.cell_user_id:
        path = f"/v1/cell/cases/{_path_part(args.case_id)}/query"
    else:
        payload["case_id"] = args.case_id
        path = "/v1/query"
    status, response = _request_json(
        base_url=args.base_url,
        method="POST",
        path=path,
        payload=payload,
        token=args.token,
        cell_secret=args.cell_secret,
        cell_user_id=args.cell_user_id,
        timeout=args.timeout,
    )
    return _print(status, response)


def cmd_retrieve(args: argparse.Namespace) -> int:
    payload = _query_payload(args)
    if args.rewrite_query:
        payload["rewrite_query"] = True
    if args.max_context_chars is not None:
        payload["max_context_chars"] = args.max_context_chars

    if args.token:
        payload["case_id"] = args.case_id
        path = "/v1/research/retrieve"
    elif args.cell_secret or args.cell_user_id:
        path = f"/v1/cell/cases/{_path_part(args.case_id)}/retrieve"
    else:
        path = f"/v1/cases/{_path_part(args.case_id)}/retrieve"
    status, response = _request_json(
        base_url=args.base_url,
        method="POST",
        path=path,
        payload=payload,
        token=args.token,
        cell_secret=args.cell_secret,
        cell_user_id=args.cell_user_id,
        timeout=args.timeout,
    )
    return _print(status, response)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Small rag_service client for humans and coding agents.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--token", help="Research bearer token.")
    parser.add_argument("--cell-secret", help="Cell gateway shared secret.")
    parser.add_argument("--cell-user-id", help="Cell gateway user id.")
    parser.add_argument("--timeout", type=float, default=30.0)

    sub = parser.add_subparsers(dest="command", required=True)

    list_cases = sub.add_parser("list-cases")
    list_cases.set_defaults(func=cmd_list_cases)

    status = sub.add_parser("status")
    status.add_argument("case_id")
    status.set_defaults(func=cmd_status)

    query = sub.add_parser("query")
    query.add_argument("case_id")
    query.add_argument("query")
    query.add_argument("--top-k", type=int)
    query.add_argument("--model-profile")
    query.add_argument("--prompt-profile-case-id")
    query.add_argument("--filters", help="JSON object.")
    query.set_defaults(func=cmd_query)

    retrieve = sub.add_parser("retrieve")
    retrieve.add_argument("case_id")
    retrieve.add_argument("query")
    retrieve.add_argument("--top-k", type=int)
    retrieve.add_argument("--model-profile")
    retrieve.add_argument("--prompt-profile-case-id")
    retrieve.add_argument("--filters", help="JSON object.")
    retrieve.add_argument("--rewrite-query", action="store_true")
    retrieve.add_argument("--max-context-chars", type=int)
    retrieve.set_defaults(func=cmd_retrieve)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except json.JSONDecodeError as exc:
        print(f"Invalid JSON: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
