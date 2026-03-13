from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

INTERVIEW_SOURCE_MARKER = "intervju"


@dataclass(frozen=True)
class AnswerModePlan:
    answer_mode: str
    source_strategy: str
    response_shape: str
    streaming_allowed: bool
    rewrite_query: bool
    use_subquery_planner: bool
    default_prompt_case_id: str | None = None
    question_set_path: str | None = None
    answer_contract: str | None = None
    planner_focus: str | None = None
    detail_level: str = "standard"
    retrieval_hint: str | None = None

    def as_trace(self) -> dict[str, object]:
        return {
            "answer_mode": self.answer_mode,
            "source_strategy": self.source_strategy,
            "response_shape": self.response_shape,
            "streaming_allowed": self.streaming_allowed,
            "rewrite_query": self.rewrite_query,
            "use_subquery_planner": self.use_subquery_planner,
            "default_prompt_case_id": self.default_prompt_case_id,
            "question_set_path": self.question_set_path,
            "detail_level": self.detail_level,
            "retrieval_hint": self.retrieval_hint,
        }


def _contains_any(message_lc: str, patterns: Iterable[str]) -> bool:
    return any(pattern in message_lc for pattern in patterns)


def _word_hits(message_lc: str, patterns: Iterable[str]) -> int:
    return sum(1 for pattern in patterns if pattern in message_lc)


INTERVIEW_PATTERNS = [
    "intervju",
    "intervjuer",
    "intervjuene",
    "respondent",
    "respondentene",
    "transkripsjon",
    "transkripsjonene",
    "lederintervju",
]

LITERATURE_PATTERNS = [
    "artikkel",
    "artikler",
    "litteratur",
    "faglitteratur",
    "teori",
    "teoretisk",
    "forskning",
    "rapport",
    "rapporter",
    "offentlige dokumenter",
    "faglig",
]

WRITING_PATTERNS = [
    "bok",
    "kapittel",
    "kapittelstruktur",
    "disposisjon",
    "manus",
    "skrive",
    "skriving",
    "utkast",
    "redaksjonell",
    "syntese",
]

DETAIL_PATTERNS = [
    "grundig",
    "detaljert",
    "vis sitater",
    "vis sitat",
    "med sitater",
    "utfyllende",
    "dypt",
]

POLICY_PATTERNS = [
    "politikk",
    "politikkområde",
    "innovasjonspolitikk",
    "virkemiddel",
    "virkemidler",
    "virkemiddelapparat",
    "fou",
    "omstilling",
    "rammebetingelse",
    "rammebetingelser",
    "norge",
]

QUESTION_FINDINGS_PATTERNS = [
    "funnene pr spørsmål",
    "funnene pr. spørsmål",
    "funn pr spørsmål",
    "funn pr. spørsmål",
    "funnene per spørsmål",
    "funn per spørsmål",
    "hva er funnene pr spørsmål",
    "hva er funnene pr. spørsmål",
    "hva er funnene per spørsmål",
    "oppsummering pr spørsmål",
    "oppsummering pr. spørsmål",
    "oppsummering per spørsmål",
    "oppsummering fra intervjuguiden",
    "oppsummering pr spørsmål fra intervjuguiden",
    "oppsummering pr. spørsmål fra intervjuguiden",
    "oppsummering per spørsmål fra intervjuguiden",
]

PER_INTERVIEW_PATTERNS = [
    "oppsummering pr intervju",
    "oppsummering pr. intervju",
    "oppsummering per intervju",
    "oppsummer pr intervju",
    "oppsummer pr. intervju",
    "oppsummer per intervju",
    "hovedtrekk pr intervju",
    "hovedtrekk pr. intervju",
    "hovedtrekk per intervju",
    "gå gjennom alle intervjuene",
    "gå igjennom alle intervjuene",
]

INTERVIEW_PATTERNS_OVERVIEW = [
    "hovedtrekk i intervjuene",
    "hovedtrekkene i intervjuene",
    "samlet viser intervjuene",
    "hva intervjuene samlet viser",
    "hva viser intervjuene",
]

INTERVIEW_GAP_PATTERNS = [
    "svakest dekning i intervjuene",
    "svak dekning i intervjuene",
    "hva mangler vi dokumentasjon på",
    "hvilke spørsmål eller temaer har svakest dekning",
]

CHAPTER_STRUCTURE_PATTERNS = [
    "kapittelstruktur",
    "struktur for kapittel",
    "forslag til kapittelstruktur",
    "disposisjon",
    "kapitteloppsett",
    "struktur for boka",
    "struktur for boken",
]

ARTICLE_HYPOTHESIS_PATTERNS = [
    "hovedhypotese",
    "hovedhypoteser",
    "arbeidshypotese",
    "arbeidshypoteser",
    "hypotese",
    "hypoteser",
    "utfordringer artikkelen bør adressere",
    "utfordringer som artikkelen bør adressere",
    "hva artikkelen bør adressere",
    "problemstillinger artikkelen bør adressere",
    "hovedutfordringer artikkelen bør adressere",
]

WORKSPACE_RECIPE_PATTERNS = [
    "arbeidsrom",
    "workspace",
    "sette sammen",
    "sammensette",
    "sammensetning",
    "komponent",
    "komponenter",
    "byggestein",
    "byggesteiner",
    "oppskrift",
    "oppskrifter",
    "router",
    "katalog",
    "prompt-admin",
    "prompt admin",
    "hvilke celler",
    "hvilken celle",
]

CASE_SWITCH_PATTERNS = [
    "research-klient",
    "research klient",
    "bytte case",
    "skifte case",
    "switch case",
    "suggested_case_id",
    "case_guidance",
    "dimy_docs og dimy_prompts",
    "dimy_docs",
    "dimy_prompts",
]


GENERAL_DIRECT_CONTRACT = """Svar direkte på spørsmålet med bare de delene som faktisk hjelper.
Bruk korte mellomtitler bare når de gjør svaret tydeligere.
Ikke bruk en fast seksjonsmal dersom spørsmålet er enkelt og faglig.
Hvis intervju og litteratur begge er relevante, skill dem tydelig.
Hvis bare én kildetype er relevant, si det eksplisitt.
Avslutt med en kort linje om hva kildene faktisk dekker og hva de ikke dekker."""


INTERVIEW_OVERVIEW_CONTRACT = """## Kort hovedfunn
Oppsummer det viktigste intervjuene samlet peker på.

## Gjennomgående trekk
Beskriv de tydeligste mønstrene på tvers av intervjuene.

## Enighet, nyanser og sprik
Skill mellom det de fleste peker på, viktige nyanser og reelle motsetninger.

## Praktisk betydning
Forklar kort hva dette betyr for bokarbeidet eller analysen.

## Hull i materialet
Pek ut hva som er svakt belagt, mangler eller trenger flere kilder."""


INTERVIEW_GAP_CONTRACT = """## Svakest dekning i intervjuene
Pek ut hvilke spørsmål, temaer eller deler av intervjuguiden som er svakest belagt i materialet.

## Hva som mangler
Si konkret hva slags dokumentasjon, eksempler, erfaringer eller motforestillinger som mangler.

## Hva dette betyr for bokarbeidet
Forklar kort hva som bør undersøkes eller suppleres før teksten blir robust.

Hold deg til innovasjonspolitikk, virkemidler, omstilling og de faktiske intervjuene.
Ikke trekk inn kode, API, systemarkitektur eller andre tekniske temaer med mindre de er eksplisitt nevnt i intervjuutdragene."""


CHAPTER_STRUCTURE_CONTRACT = """## Forslag til kapittelstruktur
List en konkret kapittel- eller avsnittsstruktur i logisk rekkefølge.

## Hvorfor denne strukturen er valgt
Forklar hvorfor denne rekkefølgen og oppbygningen er faglig og praktisk god.

## Hva som bør bygge på litteratur og hva som bør bygge på intervjuer
Skill tydelig mellom hvor litteraturgrunnlaget bør bære argumentet og hvor intervjumaterialet bør brukes.

## Svake punkter eller dokumentasjonsbehov
Pek ut hva som fortsatt trenger mer dekning før strukturen er robust."""


HYBRID_ANALYSIS_CONTRACT = """Svar med bare de seksjonene som faktisk er nyttige for spørsmålet.
Når både litteratur og intervjuer er relevante, skill tydelig mellom:
- hva litteraturen dokumenterer
- hva intervjuene viser
- hva som er nøktern syntese
Hvis brukeren ber om kort svar, svar kort.
Hvis brukeren ber om drøfting eller analyse, utvid de relevante delene."""


ARTICLE_HYPOTHESES_CONTRACT = """## Arbeidshypoteser og utfordringer for artikkelen
List 3-6 nøkterne arbeidshypoteser eller sentrale utfordringer artikkelen bør adressere.

For hvert punkt:
- formuler en presis arbeidshypotese eller utfordring
- si hvorfor dette ser viktig ut i materialet
- forklar kort hva artikkelen bør undersøke, dokumentere eller nyansere
- pek ut tydelige forbehold hvis grunnlaget er svakt eller sprikende

Ikke presenter hypotesene som etablerte sannheter. Hold dem eksplisitt som arbeidshypoteser eller analysetemaer."""


WORKSPACE_RECIPE_CONTRACT = """## Kort anbefaling
Si hvilket dokumentert arbeidsromsmønster eller hvilken dokumentert oppskrift som passer best.

## Dokumentert arbeidsromsoppskrift
Navngi det dokumenterte mønsteret eller oppsettet som dekker behovet best.

## Foreslåtte celler
List bare dokumenterte celler eller komponenter, og si kort hva kildene sier at de brukes til.

## Hvordan settes dette sammen
Beskriv et konkret oppsett i praktiske steg. Start med det enkleste dokumenterte oppsettet som dekker behovet.

## Når dette passer
Si kort hvilken type arbeidsflyt eller brukerbehov oppsettet passer for.

## Begrensninger og manglende dokumentasjon
Si tydelig hva kildene ikke dekker, eller hva som bare er svakere dokumentert.

Ikke foreslå udokumenterte celler, skjermflyter eller capabilities.
Hvis ingen dokumentert oppskrift passer godt nok, si det eksplisitt."""


WORKSPACE_CASE_SWITCH_CONTRACT = """## Kort anbefaling
Si hvilket case klienten normalt bør starte i, og når den bør bytte.

## Dokumentert klientflyt
Beskriv den dokumenterte flyten steg for steg for en research-klient som må velge mellom `dimy_docs` og `dimy_prompts`.

## Maskinlesbart signal
Forklar eksplisitt hvordan `retrieval_debug.query_plan.case_guidance` og `suggested_case_id` skal brukes når det finnes i svaret.

## Hvordan settes dette sammen
Beskriv et konkret klientmønster i praktiske steg. Start med det enkleste dokumenterte oppsettet som dekker behovet.

## Når dette passer
Si kort når klienten bør bli i valgt case, og når den bør spørre på nytt i et annet case.

## Begrensninger og manglende dokumentasjon
Si tydelig hva kildene ikke dekker, eller hva som bare er svakere dokumentert.

Ikke foreslå udokumentert klientlogikk.
Hvis case-bytte ikke er dokumentert i kildene, si det eksplisitt."""


INNOVATION_POLICY_GENERAL_FOCUS = (
    "Hold svaret innen innovasjonspolitikk, virkemidler, omstilling og praktisk politikkutforming "
    "for bokprosjektet. Hvis kildene i konteksten hovedsakelig peker mot andre innovasjonsdomener, "
    "si at dekningen er svak i stedet for å gjøre det til hovedspor."
)


INNOVATION_POLICY_RETRIEVAL_HINT = (
    "innovasjonspolitikk virkemidler virkemiddelapparat omstilling Norge FoU-politikk næringsutvikling"
)


WORKSPACE_RECIPE_RETRIEVAL_HINT = (
    "arbeidsrom workspace oppskrift RAGCaseCatalogCell RAGQueryCell "
    "RAGCorpusExplorerCell RAGDocumentLinksCell RAGCaseMembersAdminCell "
    "router katalog prompt-admin prompt admin"
)


WORKSPACE_CASE_SWITCH_RETRIEVAL_HINT = (
    "research client research-klient case_guidance suggested_case_id "
    "dimy_docs dimy_prompts /v1/research/query case bytte skifte case "
    "post /v1/research/query retrieval_debug query_plan"
)


INTERVIEW_QUESTION_SET_PATH = "config/interview_questions_innovasjonspolitikk.yml"


def _detail_level(message_lc: str) -> str:
    return "detailed" if _contains_any(message_lc, DETAIL_PATTERNS) else "standard"


def _source_groups(source_types: Iterable[str]) -> tuple[list[str], list[str]]:
    interviews: list[str] = []
    articles: list[str] = []
    for source_type in source_types:
        if INTERVIEW_SOURCE_MARKER in (source_type or "").lower():
            interviews.append(source_type)
        else:
            articles.append(source_type)
    return interviews, articles


def _is_innovation_case(case_id: str | None) -> bool:
    return bool(case_id and case_id.startswith("innovasjon"))


def choose_answer_mode(
    *,
    message: str,
    case_id: str | None,
    docs_source_types: Iterable[str],
    selected_domain: str,
) -> AnswerModePlan:
    message_lc = (message or "").strip().lower()
    detail_level = _detail_level(message_lc)
    interviews, articles = _source_groups(docs_source_types)
    interview_hits = _word_hits(message_lc, INTERVIEW_PATTERNS)
    literature_hits = _word_hits(message_lc, LITERATURE_PATTERNS)
    writing_hits = _word_hits(message_lc, WRITING_PATTERNS)
    policy_hits = _word_hits(message_lc, POLICY_PATTERNS)

    if case_id == "dimy_prompts" and _contains_any(message_lc, CASE_SWITCH_PATTERNS):
        return AnswerModePlan(
            answer_mode="workspace_recipe",
            source_strategy="articles",
            response_shape="workspace_recipe",
            streaming_allowed=False,
            rewrite_query=False,
            use_subquery_planner=False,
            default_prompt_case_id="dimy_prompts",
            answer_contract=WORKSPACE_CASE_SWITCH_CONTRACT,
            planner_focus=(
                "Prioriter dokumentert case-bytte for research-klienter, eksplisitte referanser til "
                "`case_guidance` og `suggested_case_id`, og et konkret klientforlop med minst mulig gjetning."
            ),
            detail_level=detail_level,
            retrieval_hint=WORKSPACE_CASE_SWITCH_RETRIEVAL_HINT,
        )

    if case_id == "dimy_prompts" and (
        _contains_any(message_lc, WORKSPACE_RECIPE_PATTERNS) or selected_domain == "docs"
    ):
        return AnswerModePlan(
            answer_mode="workspace_recipe",
            source_strategy="articles",
            response_shape="workspace_recipe",
            streaming_allowed=False,
            rewrite_query=False,
            use_subquery_planner=False,
            default_prompt_case_id="dimy_prompts",
            answer_contract=WORKSPACE_RECIPE_CONTRACT,
            planner_focus=(
                "Prioriter dokumenterte arbeidsromsoppskrifter, navngitte celler, konkrete steg, "
                "når oppsettet passer og tydelige begrensninger."
            ),
            detail_level=detail_level,
            retrieval_hint=WORKSPACE_RECIPE_RETRIEVAL_HINT,
        )

    if _contains_any(message_lc, QUESTION_FINDINGS_PATTERNS):
        return AnswerModePlan(
            answer_mode="interview_findings_per_question",
            source_strategy="interviews",
            response_shape="question_matrix",
            streaming_allowed=False,
            rewrite_query=False,
            use_subquery_planner=False,
            default_prompt_case_id="innovasjon_intervjuer",
            question_set_path=INTERVIEW_QUESTION_SET_PATH,
            detail_level=detail_level,
        )

    if _contains_any(message_lc, PER_INTERVIEW_PATTERNS):
        return AnswerModePlan(
            answer_mode="interview_summary_per_interview",
            source_strategy="interviews",
            response_shape="per_interview",
            streaming_allowed=False,
            rewrite_query=False,
            use_subquery_planner=False,
            default_prompt_case_id="innovasjon_intervjuer",
            detail_level=detail_level,
        )

    if _contains_any(message_lc, ARTICLE_HYPOTHESIS_PATTERNS):
        source_strategy = "hybrid" if case_id == "innovasjon_bokskriving" and interviews and articles else "interviews"
        return AnswerModePlan(
            answer_mode="article_hypotheses",
            source_strategy=source_strategy,
            response_shape="article_hypotheses",
            streaming_allowed=False,
            rewrite_query=False,
            use_subquery_planner=False,
            default_prompt_case_id="innovasjon_bokskriving" if _is_innovation_case(case_id) else case_id,
            question_set_path=INTERVIEW_QUESTION_SET_PATH,
            answer_contract=ARTICLE_HYPOTHESES_CONTRACT,
            planner_focus=(
                "Trekk ut noen få arbeidshypoteser eller sentrale utfordringer som artikkelen bør adressere, "
                "og skill tydelig mellom godt belagte mønstre og punkter som fortsatt trenger mer dokumentasjon."
            ),
            detail_level=detail_level,
        )

    if _contains_any(message_lc, CHAPTER_STRUCTURE_PATTERNS):
        source_strategy = "hybrid" if interviews and articles else ("interviews" if interviews else "articles")
        return AnswerModePlan(
            answer_mode="chapter_structure",
            source_strategy=source_strategy,
            response_shape="chapter_structure",
            streaming_allowed=False,
            rewrite_query=False,
            use_subquery_planner=True,
            default_prompt_case_id="innovasjon_bokskriving" if case_id and case_id.startswith("innovasjon") else case_id,
            answer_contract=CHAPTER_STRUCTURE_CONTRACT,
            planner_focus="Lag et retrieval-oppsett som støtter konkret kapittelstruktur og argumentasjon.",
            detail_level=detail_level,
        )

    if _contains_any(message_lc, INTERVIEW_PATTERNS_OVERVIEW):
        return AnswerModePlan(
            answer_mode="interview_main_patterns",
            source_strategy="interviews",
            response_shape="interview_overview",
            streaming_allowed=False,
            rewrite_query=False,
            use_subquery_planner=bool(interviews),
            default_prompt_case_id="innovasjon_intervjuer",
            answer_contract=INTERVIEW_OVERVIEW_CONTRACT,
            planner_focus="Prioriter brede mønstre, tydelige fellestrekk og tydelige avvik i intervjumaterialet.",
            detail_level=detail_level,
        )

    if _contains_any(message_lc, INTERVIEW_GAP_PATTERNS):
        return AnswerModePlan(
            answer_mode="interview_gap_analysis",
            source_strategy="interviews",
            response_shape="interview_gaps",
            streaming_allowed=False,
            rewrite_query=False,
            use_subquery_planner=False,
            default_prompt_case_id="innovasjon_intervjuer",
            answer_contract=INTERVIEW_GAP_CONTRACT,
            planner_focus="Prioriter hull, svak dekning, manglende dokumentasjon og tydelige forbehold i intervjumaterialet.",
            detail_level=detail_level,
        )

    if interview_hits and (literature_hits or writing_hits):
        return AnswerModePlan(
            answer_mode="hybrid_analysis",
            source_strategy="hybrid",
            response_shape="hybrid_dynamic",
            streaming_allowed=False,
            rewrite_query=False,
            use_subquery_planner=True,
            default_prompt_case_id="innovasjon_bokskriving",
            answer_contract=HYBRID_ANALYSIS_CONTRACT,
            planner_focus="Skill tydelig mellom litteraturgrunnlag, intervjufunn og nøktern syntese.",
            detail_level=detail_level,
        )

    if interview_hits or case_id == "innovasjon_intervjuer":
        return AnswerModePlan(
            answer_mode="interview_analysis",
            source_strategy="interviews",
            response_shape="direct_interview",
            streaming_allowed=False,
            rewrite_query=False,
            use_subquery_planner=False,
            default_prompt_case_id="innovasjon_intervjuer",
            answer_contract=INTERVIEW_OVERVIEW_CONTRACT,
            detail_level=detail_level,
        )

    source_strategy = "articles"
    if case_id == "innovasjon_bokskriving" and (literature_hits + writing_hits) > 0 and interviews:
        source_strategy = "hybrid" if writing_hits > literature_hits else "articles"
    innovation_policy_scope = _is_innovation_case(case_id) and source_strategy == "articles" and policy_hits > 0

    return AnswerModePlan(
        answer_mode="general",
        source_strategy=source_strategy,
        response_shape="direct",
        streaming_allowed=(selected_domain == "docs" and source_strategy == "articles"),
        rewrite_query=not innovation_policy_scope,
        use_subquery_planner=False,
        default_prompt_case_id=case_id,
        answer_contract=GENERAL_DIRECT_CONTRACT,
        planner_focus=INNOVATION_POLICY_GENERAL_FOCUS if innovation_policy_scope else None,
        detail_level=detail_level,
        retrieval_hint=INNOVATION_POLICY_RETRIEVAL_HINT if innovation_policy_scope else None,
    )


def source_types_for_strategy(source_strategy: str, docs_source_types: Iterable[str]) -> list[str]:
    interviews, articles = _source_groups(docs_source_types)
    if source_strategy == "interviews":
        return interviews
    if source_strategy == "articles":
        return articles
    if source_strategy == "hybrid":
        return list(articles) + list(interviews)
    return list(docs_source_types)


def sanitize_text_without_citations(text: str) -> str:
    cleaned = re.sub(r"\[(\d+)\]", "", text or "")
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def trim_excerpt(text: str, limit: int = 220) -> str:
    collapsed = re.sub(r"\s+", " ", (text or "")).strip()
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 1].rstrip() + "…"
