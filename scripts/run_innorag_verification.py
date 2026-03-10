from __future__ import annotations

import argparse
import json
import time
import urllib.request
from pathlib import Path
from typing import Any

import yaml


def _load_plan(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _post_json(base_url: str, payload: dict[str, Any]) -> tuple[float, dict[str, Any]]:
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/v1/query",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.monotonic()
    with urllib.request.urlopen(req, timeout=240) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    return round(time.monotonic() - started, 1), body


def _evaluate_check(item: dict[str, Any], response: dict[str, Any], seconds: float) -> dict[str, Any]:
    trace = response.get("trace") or {}
    expected = dict(item.get("expected") or {})
    checks = {
        "answer_mode": expected.get("answer_mode"),
        "source_strategy": expected.get("source_strategy"),
    }
    pass_flags = {
        key: (expected_value is None or trace.get(key) == expected_value)
        for key, expected_value in checks.items()
    }
    overall = all(pass_flags.values())
    answer = response.get("answer") or ""
    return {
        "check_id": item["check_id"],
        "question": item["question"],
        "case_id": item["case_id"],
        "seconds": seconds,
        "expected": expected,
        "actual": {
            "answer_mode": trace.get("answer_mode"),
            "source_strategy": trace.get("source_strategy"),
            "source_types_applied": trace.get("source_types_applied"),
            "citations": len(response.get("citations") or []),
        },
        "passed": overall,
        "pass_flags": pass_flags,
        "first_lines": [line for line in answer.splitlines() if line.strip()][:8],
    }


def _render_markdown(plan: dict[str, Any], results: list[dict[str, Any]]) -> str:
    lines = [f"# {plan.get('plan_id', 'InnoRAG verification')}", ""]
    passed = sum(1 for result in results if result["passed"])
    lines.append(f"- Kjoringer: {len(results)}")
    lines.append(f"- Bestatt: {passed}")
    lines.append(f"- Feilet: {len(results) - passed}")
    lines.append("")
    lines.append("| ID | Case | Expected mode | Actual mode | Expected strategy | Actual strategy | Tid | Status |")
    lines.append("| --- | --- | --- | --- | --- | --- | ---: | --- |")
    for result in results:
        lines.append(
            "| {check_id} | {case_id} | {exp_mode} | {act_mode} | {exp_strategy} | {act_strategy} | {seconds}s | {status} |".format(
                check_id=result["check_id"],
                case_id=result["case_id"],
                exp_mode=(result["expected"].get("answer_mode") or "-"),
                act_mode=(result["actual"].get("answer_mode") or "-"),
                exp_strategy=(result["expected"].get("source_strategy") or "-"),
                act_strategy=(result["actual"].get("source_strategy") or "-"),
                seconds=result["seconds"],
                status="PASS" if result["passed"] else "FAIL",
            )
        )

    for result in results:
        lines.extend(
            [
                "",
                f"## {result['check_id']} {result['question']}",
                f"- Case: `{result['case_id']}`",
                f"- Forventet: `{result['expected'].get('answer_mode')}` / `{result['expected'].get('source_strategy')}`",
                f"- Faktisk: `{result['actual'].get('answer_mode')}` / `{result['actual'].get('source_strategy')}`",
                f"- Tid: {result['seconds']}s",
                f"- Kilder: {result['actual'].get('citations')}",
                f"- Status: {'PASS' if result['passed'] else 'FAIL'}",
                "",
                "Første linjer:",
            ]
        )
        lines.extend(f"- {line}" for line in result["first_lines"])
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--plan", default="config/innorag_verification_plan.yml")
    parser.add_argument("--output-md", default="")
    parser.add_argument("--output-json", default="")
    parser.add_argument("--top-k", type=int, default=6)
    args = parser.parse_args()

    plan = _load_plan(Path(args.plan))
    results: list[dict[str, Any]] = []
    for item in list(plan.get("checks") or []):
        seconds, response = _post_json(
            args.base_url,
            {
                "query": item["question"],
                "case_id": item["case_id"],
                "top_k": args.top_k,
            },
        )
        results.append(_evaluate_check(item, response, seconds))

    if args.output_json:
        Path(args.output_json).write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    markdown = _render_markdown(plan, results)
    if args.output_md:
        Path(args.output_md).write_text(markdown, encoding="utf-8")
    print(markdown)


if __name__ == "__main__":
    main()
