from __future__ import annotations

import re
from typing import Any


_COMPOSITION_KEYWORDS = {
    "arbeidsrom",
    "workspace",
    "komponent",
    "komponenter",
    "byggestein",
    "byggesteiner",
    "celle",
    "celler",
    "oppsett",
    "sammensette",
    "sammensetning",
}

_COMPOSITION_PHRASES = (
    "sette sammen",
    "sett sammen",
    "hvordan kan jeg sette sammen",
    "hvordan setter jeg sammen",
    "valg av byggesteiner",
    "brukeroppsett",
)


def case_quick_actions(case_id: str) -> list[dict[str, str]]:
    if case_id == "innovasjon":
        return [
            {
                "label": "Litteraturgrunnlag",
                "description": "Vis et rent faglig svar fra artikler og fagstoff.",
                "prompt": "Hva sier litteraturen om helhetlig innovasjonspolitikk i Norge?",
            },
            {
                "label": "FoU vs innovasjon",
                "description": "Forklar forskjellen mellom FoU-politikk og innovasjonspolitikk.",
                "prompt": "Hva er forskjellen mellom FoU-politikk og innovasjonspolitikk?",
            },
        ]
    if case_id == "innovasjon_intervjuer":
        return [
            {
                "label": "Hovedtrekk",
                "description": "Oppsummer hovedtrekkene i intervjuene.",
                "prompt": "Hva er hovedtrekkene i intervjuene om innovasjonspolitikk og virkemidler?",
            },
            {
                "label": "Svak dekning",
                "description": "Finn temaer som er svakt belagt i intervjuene.",
                "prompt": "Hvilke spørsmål eller temaer har svakest dekning i intervjuene, og hva mangler vi dokumentasjon på?",
            },
        ]
    if case_id == "innovasjon_bokskriving":
        return [
            {
                "label": "Funn per spørsmål",
                "description": "Lister spørsmålene med oppsummering og sitater.",
                "prompt": "Hva er funnene pr spørsmål? Vis sitater.",
            },
            {
                "label": "Oppsummer per intervju",
                "description": "Vis hovedtrekk per intervju.",
                "prompt": "Gi en oppsummering pr intervju av hovedtrekkene.",
            },
            {
                "label": "Hovedtrekk i intervjuene",
                "description": "Oppsummer fellestrekk, nyanser og sprik.",
                "prompt": "Hva er hovedtrekkene i intervjuene om innovasjonspolitikk og virkemidler?",
            },
            {
                "label": "Kapittelstruktur",
                "description": "Foreslå bokkapittel basert på litteratur og intervjuer.",
                "prompt": "Lag forslag til kapittelstruktur for et bokkapittel om innovasjonspolitikk og virkemidler basert på litteratur og intervjuer, og begrunn valgene.",
            },
            {
                "label": "Faglig grunnlag",
                "description": "Vis rent faglig svar fra artiklene.",
                "prompt": "Hva sier litteraturen om helhetlig innovasjonspolitikk i Norge?",
            },
        ]
    if case_id == "dimy_docs":
        return [
            {
                "label": "API-endepunkter",
                "description": "Finn dokumenterte query-, research- og admin-endepunkter.",
                "prompt": "Hvilke API-endepunkter finnes i RAG-servicen, og hva er forskjellen mellom query, chat, admin og research?",
            },
            {
                "label": "RAGGatewayCell",
                "description": "Forklar hvordan RAGGatewayCell virker i Scaffold.",
                "prompt": "Hvordan virker RAGGatewayCell i CellScaffold, og hvilke upstream-endepunkter bruker den?",
            },
            {
                "label": "Arkitektur",
                "description": "Forklar forskjellen mellom CellProtocol, CellScaffold og rag_service.",
                "prompt": "Hva er forskjellen mellom CellProtocol, CellScaffold og rag_service, og hvordan henger de sammen?",
            },
        ]
    if case_id == "dimy_prompts":
        return [
            {
                "label": "Arbeidsrom med RAG",
                "description": "Sett sammen katalog, query og prompt-admin i ett arbeidsrom.",
                "prompt": "Hvordan setter jeg sammen et arbeidsrom med katalog, RAG og prompt-admin?",
            },
            {
                "label": "Brukerrettet dokumentasjon",
                "description": "Velg dokumenterte celler for et enkelt brukerarbeidsrom.",
                "prompt": "Hvilke dokumenterte celler bør inngå i et brukerrettet arbeidsrom for dokumentasjon?",
            },
            {
                "label": "Fast case eller router",
                "description": "Velg mellom låst case og router-oppsett.",
                "prompt": "Når bør jeg velge fast case, og når bør jeg bruke router?",
            },
            {
                "label": "Bytte case i research",
                "description": "Vis hvordan en research-klient bytter mellom dimy_docs og dimy_prompts.",
                "prompt": "Hvordan bør en research-klient bytte case mellom dimy_docs og dimy_prompts?",
            },
        ]
    return []


def case_guidance(case_id: str) -> dict[str, Any]:
    if case_id == "dimy_docs":
        return {
            "intended_for": "Utviklere og kodeassistenter som trenger API-er, kontrakter, implementasjon og tekniske begrensninger.",
            "use_when": "Bruk dette caset for dokumentert kodebruk, CellProtocol, API-er, kontrakter og runtime-adferd.",
            "avoid_when": "Ikke bruk dette caset for brukerrettet cellesammensetning eller arbeidsromsoppsett.",
            "preferred_alternative_case_id": "dimy_prompts",
            "quick_actions": case_quick_actions(case_id),
        }
    if case_id == "dimy_prompts":
        return {
            "intended_for": "Brukere som vil sette sammen celler som komponenter og velge riktig arbeidsromsoppsett.",
            "use_when": "Bruk dette caset for arbeidsrom, cellesammensetning, byggesteiner, routervalg og dokumenterte oppskrifter.",
            "avoid_when": "Ikke bruk dette caset for dype API-spørsmål, kontraktdetaljer eller teknisk implementasjon.",
            "preferred_alternative_case_id": "dimy_docs",
            "quick_actions": case_quick_actions(case_id),
        }
    if case_id in {"innovasjon", "innovasjon_intervjuer", "innovasjon_bokskriving"}:
        return {"quick_actions": case_quick_actions(case_id)}
    return {}


def looks_like_composition_question(message: str | None) -> bool:
    text = (message or "").strip().lower()
    if not text:
        return False
    if any(phrase in text for phrase in _COMPOSITION_PHRASES):
        return True
    tokens = re.findall(r"\w+", text)
    hits = sum(1 for token in tokens if token in _COMPOSITION_KEYWORDS)
    return hits >= 2


def query_case_guidance(case_id: str | None, message: str | None) -> dict[str, Any] | None:
    if case_id != "dimy_docs":
        return None
    if not looks_like_composition_question(message):
        return None
    return {
        "level": "info",
        "message": "Dette spørsmålet ser ut som brukerrettet cellesammensetning. Bruk `dimy_prompts` for arbeidsrom, byggesteiner og dokumenterte oppskrifter.",
        "suggested_case_id": "dimy_prompts",
    }
