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


def case_guidance(case_id: str) -> dict[str, str]:
    if case_id == "dimy_docs":
        return {
            "intended_for": "Utviklere og kodeassistenter som trenger API-er, kontrakter, implementasjon og tekniske begrensninger.",
            "use_when": "Bruk dette caset for dokumentert kodebruk, CellProtocol, API-er, kontrakter og runtime-adferd.",
            "avoid_when": "Ikke bruk dette caset for brukerrettet cellesammensetning eller arbeidsromsoppsett.",
            "preferred_alternative_case_id": "dimy_prompts",
        }
    if case_id == "dimy_prompts":
        return {
            "intended_for": "Brukere som vil sette sammen celler som komponenter og velge riktig arbeidsromsoppsett.",
            "use_when": "Bruk dette caset for arbeidsrom, cellesammensetning, byggesteiner, routervalg og dokumenterte oppskrifter.",
            "avoid_when": "Ikke bruk dette caset for dype API-spørsmål, kontraktdetaljer eller teknisk implementasjon.",
            "preferred_alternative_case_id": "dimy_docs",
        }
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
