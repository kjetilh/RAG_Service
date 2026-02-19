from __future__ import annotations
from typing import List
import re
from app.rag.retrieve.hybrid import RetrievedChunk

_cite_re = re.compile(r"\[(\d+)\]")

def strict_grounding_check(answer: str, sources: List[RetrievedChunk], min_citations: int = 2) -> dict:
    reasons = []
    if not answer or not answer.strip():
        return {"ok": False, "reasons": ["empty_answer"]}
    if not sources:
        return {"ok": False, "reasons": ["no_sources"]}

    # Check citation markers
    cites = [int(m.group(1)) for m in _cite_re.finditer(answer)]
    if len(cites) < min_citations:
        reasons.append(f"too_few_citations(<{min_citations})")

    # Ensure cited indices are within range
    max_idx = len(sources)
    bad = [c for c in cites if c < 1 or c > max_idx]
    if bad:
        reasons.append("citation_index_out_of_range")

    # Paragraph-level check: each non-empty paragraph should include a citation marker
    paras = [p.strip() for p in re.split(r"\n\n+", answer) if p.strip()]
    para_missing = 0
    for p in paras:
        # ignore template headings like "## Sammendrag"
        if p.startswith("#"):
            continue
        if not _cite_re.search(p):
            para_missing += 1
    if para_missing > 0:
        reasons.append(f"paragraphs_missing_citations({para_missing})")

    return {"ok": len(reasons) == 0, "reasons": reasons}
