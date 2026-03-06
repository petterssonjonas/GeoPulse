"""Briefing generation with structured progressive-disclosure sections.
"""
import json
import re
import logging
from typing import Union, Tuple
from providers import LLMProvider

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a senior geopolitical intelligence analyst with deep expertise in
international relations, military affairs, and regional politics. You produce concise,
analytically rigorous intelligence briefings. Be precise and avoid sensationalism.
Cite the sources you draw from. Your audience is a sophisticated policymaker.

Use Markdown for readability so the briefing is easy to scan: use **bold** for key terms,
names, and emphasis; use ## subheadings within long sections to break up the text; use
bullet points (- or *) for lists. Avoid walls of plain text — structure content for quick reading."""

# Depth-specific instructions injected into the template
_DEPTH_INSTRUCTIONS = {
    "brief": {
        "summary":      "2-3 sentence executive summary. Most important development first. Use **bold** for key terms.",
        "developments": "Key developments in analytical prose, 3-5 paragraphs. Use **bold** for key actors and outcomes; add ## subheadings when covering more than one distinct development. Cite sources by name. Use bullet points for lists.",
        "context":      "1-2 paragraphs of essential historical context. Use **bold** for key dates or terms where it helps.",
        "actors":       "1 paragraph covering the main actors and their positions. Use **bold** for actor names or key positions.",
        "outlook":      "1 paragraph on near-term trajectory.",
    },
    "extended": {
        "summary":      "3-4 sentence executive summary covering all major threads. Use **bold** for key terms.",
        "developments": "Comprehensive key developments, 8-14 paragraphs. Use **bold** for key actors and outcomes; use ## subheadings to separate distinct developments or themes. Cite every source by name. Use bullet points for lists. Explore nuance and competing interpretations.",
        "context":      "3-5 paragraphs of deep historical and structural context. Use **bold** and ## subheadings to break up long narrative.",
        "actors":       "2-3 paragraphs covering all relevant state and non-state actors. Use **bold** for names and key positions; bullet points for multiple actors.",
        "outlook":      "2-3 paragraphs on near-term and medium-term trajectory. Use **bold** for key scenarios; ## for distinct scenarios if helpful.",
    },
}

BRIEFING_TEMPLATE = """Analyze the following {n} recent news articles and produce a structured intelligence briefing.

Topics of focus: {topics}
Depth level: {depth_label}

Use Markdown to make the briefing easy to read: **bold** for key terms and emphasis, ## for subheadings within sections, and bullet points (- or *) for lists. Break up long prose so a reader can scan quickly.

ARTICLES:
{articles}

Respond in EXACTLY this format, keeping the <<<MARKERS>>>:

<<<SEVERITY>>>
[integer 1-5: 1=routine, 2=low, 3=moderate, 4=high, 5=critical. Reserve 5 ONLY for events that directly threaten large-scale loss of life, WMD use, or existential-level crises affecting mankind or very large populations. Do not use 5 for serious but contained or regional crises.]

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

<<<TOPICS>>>
[Up to 4 topic labels most relevant to THIS briefing, ranked by relevance (most relevant first). Use the "Topics of focus" above or short labels from the story (e.g. region, conflict, actor). One per line or comma-separated. No filler — only topics that directly describe this story. You may output 1, 2, 3, or 4 topics.]

<<<END>>>"""


# Novelty check: should we generate a new briefing, skip, or attach an update to an earlier one?
NOVELTY_CHECK_PROMPT = """You are a geopolitical intelligence analyst. Your task is to decide whether new articles warrant a new briefing.

RECENT BRIEFINGS (already shown to the user):
{recent_briefings}

NEW ARTICLES:
{articles}

Consider: Is there GENUINE new information that affects mankind or large populations, or a genuinely new/breaking story? Or is this mostly the same story as an earlier briefing with only minor updates or rehashed coverage?

Reply with EXACTLY one of these lines (nothing else):
- SKIP — if there is no real new information; just more of the same or fluff.
- NEW — if there is a genuinely new story or major new development deserving a full new briefing.
- UPDATE <id> — if the new articles are minor updates to one of the recent briefings above; use that briefing's id number. Only use UPDATE if the same story is already covered and there are only small updates.

Examples: "SKIP", "NEW", "UPDATE 12" """


def check_novelty(articles: list, recent_briefings: list, provider: LLMProvider) -> Union[str, Tuple[str, int]]:
    """Returns 'skip', 'full', or ('update', parent_briefing_id)."""
    if not recent_briefings:
        return "full"
    articles_text = format_articles_for_prompt(articles[:15])
    briefings_text = "\n\n".join(
        f"[ID {b['id']}] {b.get('headline', '')}\n{b.get('summary', '')[:400]}"
        for b in recent_briefings
    )
    prompt = NOVELTY_CHECK_PROMPT.format(
        recent_briefings=briefings_text,
        articles=articles_text,
    )
    response = provider.chat([{"role": "user", "content": prompt}])
    if not response or not isinstance(response, str):
        return "full"
    response = response.strip().upper()
    if "SKIP" in response:
        return "skip"
    if response.startswith("UPDATE"):
        import re
        m = re.search(r"UPDATE\s+(\d+)", response)
        if m:
            return ("update", int(m.group(1)))
    return "full"


# Short template for update sub-cards (minor updates to an earlier briefing)
UPDATE_BRIEFING_TEMPLATE = """The following articles are MINOR UPDATES to a story already briefed. Produce a very short update only.

Earlier briefing headline: {parent_headline}

NEW ARTICLES:
{articles}

Reply in this format:

<<<HEADLINE>>>
[One short line: "Update: ..." or "Latest: ..." — max 10 words]

<<<SUMMARY>>>
[2-4 sentences max: only what is NEW or changed. Use **bold** for key points.]

<<<DEVELOPMENTS>>>
[Optional: 1-2 paragraphs only if needed. Otherwise leave empty or repeat summary.]

<<<SEVERITY>>>
[Same as parent or 1-5 if changed]

<<<END>>>"""


def generate_update_briefing(articles: list, parent_briefing: dict, provider: LLMProvider) -> dict | None:
    """Generate a short update briefing that attaches to parent_briefing. Returns None on parse failure."""
    articles_text = format_articles_for_prompt(articles[:10])
    prompt = UPDATE_BRIEFING_TEMPLATE.format(
        parent_headline=parent_briefing.get("headline", "Earlier briefing"),
        articles=articles_text,
    )
    response = provider.chat([{"role": "user", "content": prompt}])
    if not response or not isinstance(response, str):
        return None
    headline = _extract_section(response, "HEADLINE")
    summary = _extract_section(response, "SUMMARY")
    developments = _extract_section(response, "DEVELOPMENTS")
    severity_raw = _extract_section(response, "SEVERITY")
    try:
        severity = max(1, min(5, int("".join(c for c in severity_raw if c.isdigit())[:1] or "1")))
    except (ValueError, TypeError):
        severity = parent_briefing.get("severity", 2)
    if not headline or not summary:
        return None
    return {
        "headline": headline.strip(),
        "summary": summary.strip(),
        "developments": developments.strip() if developments else summary.strip(),
        "context": "",
        "actors": "",
        "outlook": "",
        "watch_indicators": [],
        "suggested_questions": [],
        "severity": severity,
        "confidence": "medium",
        "article_ids": [a["id"] for a in articles if "id" in a],
        "source_count": len(set(a.get("source_name", "") for a in articles)),
        "briefing_type": "update",
        "parent_briefing_id": parent_briefing["id"],
        "topics": ["Update"],
    }


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
        "<<<OUTLOOK>>>", "<<<WATCH>>>", "<<<QUESTIONS>>>", "<<<TOPICS>>>", "<<<END>>>",
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

    result = {
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
        "topics_raw": _extract_section(text, "TOPICS"),
    }
    raw = result.get("topics_raw", "").strip()
    result["topics"] = _parse_topics_line(raw)
    del result["topics_raw"]
    return result


def _parse_topics_line(raw: str) -> list:
    """Parse TOPICS section into up to 4 topic strings (comma or newline separated)."""
    if not raw:
        return []
    out = []
    for part in re.split(r"[\n,]+", raw):
        part = part.strip().strip('"\'')
        if part and part not in out:
            out.append(part)
            if len(out) >= 4:
                break
    return out[:4]


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
    # If AI gave fewer than 4 topics, fill from article aggregation (ranked by frequency)
    if len(parsed.get("topics", [])) < 4:
        from collections import Counter
        all_t = []
        for a in articles:
            all_t.extend(a.get("topics") or [])
        for t, _ in Counter(all_t).most_common(4):
            if t and t not in parsed.get("topics", []):
                parsed.setdefault("topics", []).append(t)
                if len(parsed["topics"]) >= 4:
                    break
    parsed["topics"] = (parsed.get("topics") or [])[:5]
    return parsed
