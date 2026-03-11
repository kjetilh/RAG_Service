from app.rag.cases.guidance import case_guidance, looks_like_composition_question, query_case_guidance


def test_case_guidance_for_doc_cases_is_explicit():
    docs = case_guidance("dimy_docs")
    prompts = case_guidance("dimy_prompts")

    assert docs["preferred_alternative_case_id"] == "dimy_prompts"
    assert prompts["preferred_alternative_case_id"] == "dimy_docs"


def test_looks_like_composition_question_detects_workspace_queries():
    assert looks_like_composition_question("Hvordan kan jeg sette sammen celler som komponenter for et arbeidsrom?")
    assert not looks_like_composition_question("Hvordan virker /v1/query i doc-tjenesten?")


def test_query_case_guidance_redirects_dimy_docs_composition_questions():
    hint = query_case_guidance("dimy_docs", "Hvordan setter jeg sammen celler i et arbeidsrom?")
    assert hint is not None
    assert hint["suggested_case_id"] == "dimy_prompts"

    assert query_case_guidance("dimy_prompts", "Hvordan setter jeg sammen celler?") is None
