from app.rag.planner.answer_modes import (
    WORKSPACE_CASE_SWITCH_CONTRACT,
    WORKSPACE_RECIPE_CONTRACT,
    choose_answer_mode,
    source_types_for_strategy,
)


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
        docs_source_types=["innovasjonsledelse", "innovasjonsfag", "innovasjon_intervju_transcript"],
        selected_domain="docs",
    )

    assert plan.answer_mode == "chapter_structure"
    assert plan.source_strategy == "hybrid"
    assert plan.use_subquery_planner is True
    assert plan.default_prompt_case_id == "innovasjon_bokskriving"


def test_choose_answer_mode_detects_article_hypotheses_for_book_case():
    plan = choose_answer_mode(
        message="Lag noen hovedhypoteser og utfordringer som artikkelen bør adressere basert på intervjuene og materialet ellers.",
        case_id="innovasjon_bokskriving",
        docs_source_types=["innovasjonsledelse", "innovasjonsfag", "innovasjon_intervju_transcript"],
        selected_domain="docs",
    )

    assert plan.answer_mode == "article_hypotheses"
    assert plan.source_strategy == "hybrid"
    assert plan.streaming_allowed is False
    assert plan.question_set_path == "config/interview_questions_innovasjonspolitikk.yml"
    assert "arbeidshypoteser" in (plan.answer_contract or "")


def test_choose_answer_mode_keeps_interview_gap_question_in_interview_lane():
    plan = choose_answer_mode(
        message="Hvilke spørsmål eller temaer har svakest dekning i intervjuene, og hva mangler vi dokumentasjon på?",
        case_id="innovasjon_bokskriving",
        docs_source_types=["innovasjonsledelse", "innovasjonsfag", "innovasjon_intervju_transcript"],
        selected_domain="docs",
    )

    assert plan.answer_mode == "interview_gap_analysis"
    assert plan.source_strategy == "interviews"
    assert plan.streaming_allowed is False
    assert "Svakest dekning i intervjuene" in (plan.answer_contract or "")


def test_choose_answer_mode_treats_detailed_per_interview_as_detailed():
    plan = choose_answer_mode(
        message="Gå igjennom alle intervjuene og lag en detaljert oppsummering pr. intervju.",
        case_id="innovasjon_bokskriving",
        docs_source_types=["innovasjonsledelse", "innovasjonsfag", "innovasjon_intervju_transcript"],
        selected_domain="docs",
    )

    assert plan.answer_mode == "interview_summary_per_interview"
    assert plan.source_strategy == "interviews"
    assert plan.detail_level == "detailed"


def test_choose_answer_mode_adds_policy_focus_for_innovation_policy_questions():
    plan = choose_answer_mode(
        message="Hvorfor er innovasjon et legitimt politikkområde i Norge?",
        case_id="innovasjon_bokskriving",
        docs_source_types=["innovasjonsledelse", "innovasjonsfag", "innovasjon_intervju_transcript"],
        selected_domain="docs",
    )

    assert plan.answer_mode == "general"
    assert plan.source_strategy == "articles"
    assert plan.rewrite_query is False
    assert "innovasjonspolitikk" in (plan.planner_focus or "")
    assert "virkemidler" in (plan.retrieval_hint or "")


def test_choose_answer_mode_does_not_force_hybrid_for_interview_only_question_in_book_case():
    plan = choose_answer_mode(
        message="Hvilke intervjuer peker tydeligst på fragmentering i virkemiddelapparatet? Vis sitater.",
        case_id="innovasjon_bokskriving",
        docs_source_types=["innovasjonsledelse", "innovasjonsfag", "innovasjon_intervju_transcript"],
        selected_domain="docs",
    )

    assert plan.source_strategy == "interviews"
    assert plan.answer_mode == "interview_analysis"


def test_source_types_for_strategy_splits_interviews_and_articles():
    source_types = ["innovasjonsledelse", "innovasjonsfag", "innovasjon_intervju_transcript"]

    assert source_types_for_strategy("articles", source_types) == ["innovasjonsledelse", "innovasjonsfag"]
    assert source_types_for_strategy("interviews", source_types) == ["innovasjon_intervju_transcript"]
    assert source_types_for_strategy("hybrid", source_types) == source_types


def test_choose_answer_mode_uses_workspace_recipe_for_dimy_prompts_case():
    plan = choose_answer_mode(
        message="Hvordan setter jeg sammen et arbeidsrom med katalog, RAG og prompt-admin?",
        case_id="dimy_prompts",
        docs_source_types=["prompt_docs"],
        selected_domain="docs",
    )

    assert plan.answer_mode == "workspace_recipe"
    assert plan.source_strategy == "articles"
    assert plan.streaming_allowed is False
    assert plan.rewrite_query is False
    assert plan.default_prompt_case_id == "dimy_prompts"
    assert plan.answer_contract == WORKSPACE_RECIPE_CONTRACT
    assert "RAGQueryCell" in (plan.retrieval_hint or "")


def test_choose_answer_mode_uses_case_switch_contract_for_dimy_prompts_research_client_question():
    plan = choose_answer_mode(
        message="Hvordan bør en research-klient bytte case mellom dimy_docs og dimy_prompts?",
        case_id="dimy_prompts",
        docs_source_types=["prompt_docs"],
        selected_domain="docs",
    )

    assert plan.answer_mode == "workspace_recipe"
    assert plan.source_strategy == "articles"
    assert plan.streaming_allowed is False
    assert plan.rewrite_query is False
    assert plan.default_prompt_case_id == "dimy_prompts"
    assert plan.answer_contract == WORKSPACE_CASE_SWITCH_CONTRACT
    assert "case_guidance" in (plan.retrieval_hint or "")
