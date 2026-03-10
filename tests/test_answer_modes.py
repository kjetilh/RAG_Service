from app.rag.planner.answer_modes import choose_answer_mode, source_types_for_strategy


def test_choose_answer_mode_detects_question_findings():
    plan = choose_answer_mode(
        message="Hva er funnene pr spørsmål? Vis sitater.",
        case_id="innovasjon_bokskriving",
        docs_source_types=["innovasjonsledelse", "innovasjon_intervju_transcript"],
        selected_domain="docs",
    )

    assert plan.answer_mode == "interview_findings_per_question"
    assert plan.source_strategy == "interviews"
    assert plan.streaming_allowed is False
    assert plan.question_set_path == "config/interview_questions_innovasjonspolitikk.yml"


def test_choose_answer_mode_detects_chapter_structure_and_hybrid_strategy():
    plan = choose_answer_mode(
        message="Lag forslag til kapittelstruktur for boka om innovasjonspolitikk basert på intervjuer og litteratur.",
        case_id="innovasjon_bokskriving",
        docs_source_types=["innovasjonsledelse", "immovasjonsfag", "innovasjon_intervju_transcript"],
        selected_domain="docs",
    )

    assert plan.answer_mode == "chapter_structure"
    assert plan.source_strategy == "hybrid"
    assert plan.use_subquery_planner is True
    assert plan.default_prompt_case_id == "innovasjon_bokskriving"


def test_source_types_for_strategy_splits_interviews_and_articles():
    source_types = ["innovasjonsledelse", "immovasjonsfag", "innovasjon_intervju_transcript"]

    assert source_types_for_strategy("articles", source_types) == ["innovasjonsledelse", "immovasjonsfag"]
    assert source_types_for_strategy("interviews", source_types) == ["innovasjon_intervju_transcript"]
    assert source_types_for_strategy("hybrid", source_types) == source_types
