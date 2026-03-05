"""Briefing generation with structured progressive-disclosure sections.

Parsing is designed for reliable results: marker-based extraction with fallbacks
so malformed or non-compliant model output still yields a usable briefing. For
consistent event/story classification across runs, we may later recommend or
support a single "GeoPulse" model; different models can disagree on whether
stories are the same event.
"""
import json
import re
import logging
from providers import LLMProvider

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a senior geopolitical intelligence analyst with deep expertise in
international relations, military affairs, and regional politics. You produce concise,
analytically rigorous intelligence briefings. Be precise and avoid sensationalism.
Cite the sources you draw from. Your audience is a sophisticated policymaker."""

# Depth-specific instructions injected into the template
_DEPTH_INSTRUCTIONS = {
    "brief": {
        "summary":      "2-3 sentence executive summary. Most important development first.",
        "developments": "Key developments in analytical prose, 3-5 paragraphs. Cite sources by name.",
        "context":      "1-2 paragraphs of essential historical context.",
        "actors":       "1 paragraph covering the main actors and their positions.",
        "outlook":      "1 paragraph on near-term trajectory.",
    },
    "extended": {
        "summary":      "3-4 sentence executive summary covering all major threads.",
        "developments": "Comprehensive key developments, 8-14 paragraphs. Cite every source by name. Explore nuance and competing interpretations.",
        "context":      "3-5 paragraphs of deep historical and structural context.",
        "actors":       "2-3 paragraphs covering all relevant state and non-state actors, their interests, red lines, and likely intentions.",
        "outlook":      "2-3 paragraphs on near-term and medium-term trajectory, including divergent scenarios.",
    },
}

BRIEFING_TEMPLATE = """Analyze the following {n} recent news articles and produce a structured intelligence briefing.

Topics of focus: {topics}
Depth level: {depth_label}

ARTICLES:
{articles}

Respond in EXACTLY this format, keeping the <<<MARKERS>>>:

<<<SEVERITY>>>
[integer 1-5: 1=routine, 2=low, 3=moderate, 4=high, 5=critical]

<<<CONFIDENCE>>>
[low, medium, or high — based on source count and corroboration]

<<<HEADLINE>>>
[Single punchy intelligence headline, max 12 words]

<<<SUMMARY>>>
[{inst_summary}]

<<<DEVELOPMENTS>>>
[{inst_developments}]

<<<CONTEXT>>>
[{inst_context}]

<<<ACTORS>>>
[{inst_actors}]

<<<OUTLOOK>>>
[{inst_outlook}]

<<<WATCH>>>
["Specific indicator to monitor 1", "Specific indicator to monitor 2", "Specific indicator to monitor 3"]

<<<QUESTIONS>>>
["Specific analytical follow-up question 1?", "Specific analytical follow-up question 2?", "Specific analytical follow-up question 3?"]

<<<END>>>"""


def format_articles_for_prompt(articles: list) -> str:
    parts = []
    for i, a in enumerate(articles, 1):
        pub = a.get("published_at", "")[:16] if a.get("published_at") else ""
        text = a.get("full_text") or a.get("summary", "")[:500]
        parts.append(
            f"[{i}] {a.get('source_name', '?')} | {pub}\n"
            f"TITLE: {a['title']}\n"
            f"{text}\n"
            f"URL: {a['url']}"
        )
    return "\n---\n".join(parts)


def _extract_section(text: str, marker: str) -> str:
    markers = [
        "<<<SEVERITY>>>", "<<<CONFIDENCE>>>", "<<<HEADLINE>>>", "<<<SUMMARY>>>",
        "<<<DEVELOPMENTS>>>", "<<<CONTEXT>>>", "<<<ACTORS>>>",
        "<<<OUTLOOK>>>", "<<<WATCH>>>", "<<<QUESTIONS>>>", "<<<END>>>",
    ]
    start_tag = f"<<<{marker}>>>"
    if start_tag not in markers:
        return ""
    start = text.find(start_tag)
    if start == -1:
        return ""
    start += len(start_tag)
    idx = markers.index(start_tag)
    end = len(text)
    for next_marker in markers[idx + 1:]:
        pos = text.find(next_marker, start)
        if pos != -1:
            end = pos
            break
    raw = text[start:end].strip()
    # Strip markdown code fences some models add
    if raw.startswith("```") and "```" in raw[3:]:
        raw = raw[3:].split("```", 1)[0].strip()
    return raw


def _parse_json_list(raw: str) -> list:
    """Parse a list from model output: JSON array, or bullet lines, or quoted strings."""
    if not (raw and raw.strip()):
        return []
    s = raw.strip()
    # 1) JSON array
    try:
        out = json.loads(s)
        if isinstance(out, list):
            return [str(x).strip() for x in out if str(x).strip()][:10]
    except (json.JSONDecodeError, ValueError, TypeError):
        pass
    # 2) Lines starting with - or * or number.
    lines = []
    for line in s.splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^[\-\*]\s*(.+)", line) or re.match(r"^\d+[\.\)]\s*(.+)", line)
        if m:
            lines.append(m.group(1).strip())
    if lines:
        return lines[:10]
    # 3) Double-quoted strings
    quoted = re.findall(r'"([^"]+)"', s)
    if quoted:
        return [q.strip() for q in quoted if q.strip()][:10]
    # 4) Single-quoted
    quoted = re.findall(r"'([^']+)'", s)
    if quoted:
        return [q.strip() for q in quoted if q.strip()][:10]
    return []


def parse_briefing_response(text: str) -> dict:
    severity_raw = _extract_section(text, "SEVERITY")
    try:
        severity = int("".join(c for c in severity_raw if c.isdigit())[:1] or "1")
        severity = max(1, min(5, severity))
    except (ValueError, IndexError):
        severity = 1

    confidence = _extract_section(text, "CONFIDENCE").lower().strip()
    if confidence not in ("low", "medium", "high"):
        confidence = "medium"

    return {
        "severity": severity,
        "confidence": confidence,
        "headline": _extract_section(text, "HEADLINE"),
        "summary": _extract_section(text, "SUMMARY"),
        "developments": _extract_section(text, "DEVELOPMENTS"),
        "context": _extract_section(text, "CONTEXT"),
        "actors": _extract_section(text, "ACTORS"),
        "outlook": _extract_section(text, "OUTLOOK"),
        "watch_indicators": _parse_json_list(_extract_section(text, "WATCH"))[:5],
        "suggested_questions": _parse_json_list(_extract_section(text, "QUESTIONS"))[:4],
    }


def _first_line_like_headline(text: str, max_len: int = 200) -> str:
    """First non-empty line that does not look like a marker or instruction."""
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("<<<") or len(line) > max_len:
            continue
        if re.match(r"^\[?\d*[\.\)]\s*", line):
            line = re.sub(r"^\[?\d*[\.\)]\s*", "", line).strip()
        if line:
            return line[:200]
    return ""


def _fallback_headline(parsed: dict, raw_response: str, articles: list) -> None:
    if parsed.get("headline", "").strip():
        return
    candidate = _first_line_like_headline(raw_response)
    if candidate:
        parsed["headline"] = candidate
        logger.debug("Fallback: headline from first line of response")
        return
    if articles:
        first_title = (articles[0].get("title") or "").strip()
        if first_title:
            parsed["headline"] = first_title[:120]
            logger.debug("Fallback: headline from first article title")
            return
    parsed["headline"] = f"Key developments from {len(articles)} sources"


def _fallback_summary(parsed: dict, raw_response: str, articles: list) -> None:
    if parsed.get("summary", "").strip():
        return
    dev = parsed.get("developments", "").strip()
    if dev:
        first_para = dev.split("\n\n")[0].strip()[:500]
        if first_para:
            parsed["summary"] = first_para
            logger.debug("Fallback: summary from first paragraph of developments")
            return
    for a in articles[:3]:
        s = (a.get("summary") or a.get("full_text") or "").strip()
        if s:
            parsed["summary"] = s[:400] + ("…" if len(s) > 400 else "")
            logger.debug("Fallback: summary from first article")
            return
    parsed["summary"] = "See developments below."


def _fallback_developments(parsed: dict, raw_response: str, articles: list) -> None:
    if parsed.get("developments", "").strip():
        return
    ctx = parsed.get("context", "").strip()
    if ctx:
        parsed["developments"] = ctx
        logger.debug("Fallback: developments from context")
        return
    parts = []
    for i, a in enumerate(articles[:5], 1):
        title = (a.get("title") or "").strip()
        summary = (a.get("summary") or a.get("full_text") or "").strip()[:200]
        if title:
            parts.append(f"[{i}] {title}\n{summary}")
    if parts:
        parsed["developments"] = "\n\n".join(parts)
        logger.debug("Fallback: developments from article titles and summaries")


def apply_parsing_fallbacks(parsed: dict, raw_response: str, articles: list) -> None:
    """Fill empty required fields from raw response or article list. Mutates parsed."""
    _fallback_headline(parsed, raw_response, articles)
    _fallback_summary(parsed, raw_response, articles)
    _fallback_developments(parsed, raw_response, articles)


def validate_briefing(parsed: dict) -> None:
    """Raise ValueError if the briefing is not usable (e.g. empty headline)."""
    headline = (parsed.get("headline") or "").strip()
    if not headline:
        raise ValueError(
            "LLM produced no parseable briefing (missing headline). "
            "Try a conversational model that follows instructions, or retry later."
        )


def generate_briefing(articles: list, topics: list, provider: LLMProvider,
                      depth: str = "brief") -> dict:
    depth = depth if depth in _DEPTH_INSTRUCTIONS else "brief"
    inst = _DEPTH_INSTRUCTIONS[depth]
    articles_text = format_articles_for_prompt(articles)
    prompt = BRIEFING_TEMPLATE.format(
        n=len(articles),
        topics=", ".join(topics) if topics else "general geopolitics",
        depth_label=depth.upper(),
        inst_summary=inst["summary"],
        inst_developments=inst["developments"],
        inst_context=inst["context"],
        inst_actors=inst["actors"],
        inst_outlook=inst["outlook"],
        articles=articles_text,
    )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
    response = provider.chat(messages)
    if response is None:
        response = ""
    if not isinstance(response, str):
        response = str(response) if response else ""
    parsed = parse_briefing_response(response)
    apply_parsing_fallbacks(parsed, response, articles)
    validate_briefing(parsed)
    parsed["article_ids"] = [a["id"] for a in articles if "id" in a]
    return parsed
