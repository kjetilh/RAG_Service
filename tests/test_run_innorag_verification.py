from pathlib import Path

from scripts.run_innorag_verification import _evaluate_check, _load_plan, _render_markdown


def test_load_plan_reads_yaml(tmp_path: Path):
    plan_path = tmp_path / "plan.yml"
    plan_path.write_text(
        "version: 1\nplan_id: test_plan\nchecks:\n  - check_id: A1\n    case_id: innovasjon\n    question: Hei\n",
        encoding="utf-8",
    )

    plan = _load_plan(plan_path)

    assert plan["plan_id"] == "test_plan"
    assert plan["checks"][0]["check_id"] == "A1"


def test_evaluate_check_marks_expected_mode_and_strategy():
    result = _evaluate_check(
        {
            "check_id": "A1",
            "question": "Hei",
            "case_id": "innovasjon",
            "expected": {"answer_mode": "general", "source_strategy": "articles"},
        },
        {
            "trace": {"answer_mode": "general", "source_strategy": "articles", "source_types_applied": ["innovasjonsledelse"]},
            "citations": [{"doc_id": "d1"}],
            "answer": "Kort svar\nDetalj",
        },
        1.2,
    )

    assert result["passed"] is True
    assert result["actual"]["citations"] == 1


def test_render_markdown_contains_summary_table():
    markdown = _render_markdown(
        {"plan_id": "test_plan"},
        [
            {
                "check_id": "A1",
                "question": "Hei",
                "case_id": "innovasjon",
                "seconds": 1.2,
                "expected": {"answer_mode": "general", "source_strategy": "articles"},
                "actual": {"answer_mode": "general", "source_strategy": "articles", "citations": 1},
                "passed": True,
                "pass_flags": {"answer_mode": True, "source_strategy": True},
                "first_lines": ["Kort svar"],
            }
        ],
    )

    assert "# test_plan" in markdown
    assert "| A1 | innovasjon | general | general | articles | articles | 1.2s | PASS |" in markdown
