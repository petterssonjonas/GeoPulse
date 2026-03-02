"""Briefing generation with structured progressive-disclosure sections."""
import json
import re
from providers import LLMProvider

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
    return text[start:end].strip()


def _parse_json_list(raw: str) -> list:
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return re.findall(r'"([^"]+)"', raw)


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
    parsed = parse_briefing_response(response)
    parsed["article_ids"] = [a["id"] for a in articles if "id" in a]
    return parsed
