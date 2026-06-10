"""
injection_guard.py — heuristic prompt-injection / instruction-override detection
for inbound email (Phase 4C).

Untrusted email text flows into action-taking LLM agents, so before the pipeline
treats a request as autonomous we screen it for classic injection patterns. A hit
does NOT hard-block — it forces the task to human review (isAutonomous=False), so a
person vets it before any action runs. (The structural recipient defense from
Phase 1 already prevents output-redirection regardless.)

This is intentionally a fast, deterministic heuristic — not an LLM — so it can't
itself be prompt-injected and adds no latency/cost.
"""
import re

_PATTERNS = [
    r"ignore\s+(all\s+|any\s+)?(previous|prior|above|earlier|the\s+above)\s+instructions",
    r"disregard\s+(the\s+)?(above|previous|prior|all|earlier)",
    r"forget\s+(everything|all|your\s+instructions|previous\s+instructions)",
    r"\byou\s+are\s+now\b",
    r"\bact\s+as\s+(an?\s+|the\s+)?",
    r"new\s+instructions?\s*[:\-]",
    r"\bsystem\s+prompt\b",
    r"\bdeveloper\s+mode\b",
    r"override\s+(the\s+)?(rules|policy|policies|system|instructions|guardrails)",
    r"do\s+not\s+follow\s+(the\s+)?(rules|policy|instructions)",
    r"(reveal|print|show|repeat)\s+(your\s+)?(the\s+)?(system\s+)?(prompt|instructions)",
    r"pretend\s+(to\s+be|you\s+are)",
]
_COMPILED = [re.compile(p, re.IGNORECASE) for p in _PATTERNS]


def screen(text: str) -> tuple[bool, list[str]]:
    """Return (flagged, matched_snippets) for prompt-injection heuristics."""
    if not text:
        return False, []
    hits: list[str] = []
    for rx in _COMPILED:
        m = rx.search(text)
        if m:
            snippet = m.group(0).strip()
            if snippet not in hits:
                hits.append(snippet)
    return (len(hits) > 0), hits
