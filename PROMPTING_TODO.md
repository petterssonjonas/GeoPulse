# GeoPulse — Prompting TODO

Prompting work is tracked separately from programming. The challenge here is analytical and editorial — what to ask the model, when, how to structure context, how to get reliable and intellectually honest output. Programming implementation of these ideas is tracked in `TODO.md`.

---

## Current Prompts (in `analysis/briefing.py`)

Four prompts currently exist, all editable by the user in Settings → Prompts:

| ID | When it runs | Current status |
|----|-------------|----------------|
| `system_prompt` | System message for every full briefing | Functional; needs constitution integration |
| `briefing_template` | Full briefing generation | Functional; marker-based parsing (`<<<MARKERS>>>`) |
| `novelty_check_prompt` | Before each briefing, decides SKIP / NEW / UPDATE | Functional; fragile response parsing |
| `update_briefing_template` | Minor updates to existing briefings | Functional; minimal |

---

## 1. Constitution and Analyst Identity

The `Geopulse_constitution.md` file defines the epistemic framework and analytical principles for the GeoPulse analyst persona. It needs to be woven into the prompt architecture, not just exist as a file.

**Decisions needed:**

- **Where does it live in the message structure?**
  - Option A: Prepend the full constitution to `system_prompt`. Clean but long; may dilute the analyst role if the model front-loads it.
  - Option B: Inject the constitution as a separate `system` message before the analyst `system_prompt`. Gives it its own weight.
  - Option C: Reference a condensed version in `system_prompt`, keep the full document for RAG retrieval only.
  - Likely best: a condensed "analyst principles" block in `system_prompt`, with the `data/context/` files available for RAG injection when relevant.

- **How much of the constitution goes into every call vs. retrieved only when relevant?**
  - The epistemic framework (intellectual humility, framing consensus) should be in every call — it shapes tone and hedging.
  - The anchor contexts (Century of Humiliation, Varangian Rus, etc.) should only be injected when the briefing topic is relevant — don't waste context window on China anchors when briefing a South America event.

- **Trigger logic for anchor injection:** When assembling the briefing prompt, detect which anchors are relevant based on article topics/regions and inject only those `data/context/` excerpts. E.g. articles mentioning China, Taiwan, Hong Kong, or Xinjiang → inject `china_historical_frame.md`. This is a prompting decision (what to inject) as much as a programming one.

**Draft condensed system prompt addition:**
```
Analytical principles:
- Distinguish what is known, inferred, and speculated. Signal epistemic status explicitly.
- Frame contested claims as consensus, not fact: "Western analysts assess...", "The Russian government's position is...", "Within the Chinese national tradition..."
- Hold multiple interpretive frames simultaneously. Name the frame you are using.
- Flag when sources are structurally limited (anglophone-only, no regional voices).
- Apply anchor contexts where relevant: Century of Humiliation (China), Varangian Rus/Putin's temporal frame (Russia/Ukraine), Partition (South Asia), Ottoman mandate legacy (Middle East).
```

---

## 2. Article Cleaning Pass

The plan: before articles reach the briefing prompt, run a single LLM cleaning pass to strip HTML artifacts, boilerplate (cookie banners, subscribe prompts, navigation text), and irrelevant filler, and return clean prose.

**Prompt to design:**
- Input: raw article text (may include HTML fragments, boilerplate)
- Output: clean prose only — no summarization, no analysis, preserve all facts
- Should be a short, instruction-following prompt, not an analyst prompt
- The cleaning model can be a different (faster/smaller) model than the briefing model — worth a config option (`triage_model` already exists in config)

**Key prompt constraint:** The cleaning pass must not add inference or opinion. It is purely editorial — "remove noise, preserve signal." A poorly designed cleaning prompt that summarizes rather than cleans will silently lose facts before the briefing sees them.

**Draft:**
```
You are a text cleaner. Remove HTML fragments, cookie notices, navigation text, advertisement copy, subscription prompts, and other boilerplate from the following article text. Preserve all factual content, quotes, names, dates, and numbers exactly as written. Do not summarize, infer, or add anything. Return only the cleaned article text.

TEXT:
{raw_text}
```

---

## 3. Novelty Check Refinement

The current novelty check prompt is functional but has some gaps:

- It currently only sees article titles + summaries (truncated to 15 articles, 400 chars per briefing). It may miss novelty in the full article text.
- The SKIP/NEW/UPDATE instruction relies on the model parsing its own response; some models pad the response and break the parser. Consider adding: "Reply on the first line only."
- **Threshold calibration:** The current prompt is fairly aggressive about returning SKIP. In practice, if the model is too conservative on NEW, users see sparse briefings. If too liberal, they see noise. This needs testing across models.
- **UPDATE without a parent:** Some models return UPDATE with an ID that doesn't exist. The parser handles this gracefully (falls back to full), but the prompt should explicitly say "only use UPDATE <id> with an ID from the list above."

---

## 4. Structured Output: Replacing Markers with Pydantic

The current `<<<MARKERS>>>` format was chosen for reliability with smaller local models. The fallback parser in `parse_briefing_response()` handles malformed output but produces degraded results. Consider a Pydantic-first approach for cloud providers:

- When provider is Anthropic or OpenAI, request JSON output and validate with a Pydantic `BriefingResponse` model. Cleaner, no regex needed.
- Keep the marker-based format for Ollama where JSON mode is less consistent across models.
- This is a branched strategy: same logical prompt, different output format instruction based on provider type.

**Open question:** Should this be opt-in per provider, or automatic? Automatic is cleaner; opt-in is safer while JSON mode reliability on local models is still variable.

---

## 5. Context Window Budget

Every briefing prompt assembles: system prompt + (optionally) constitution excerpt + anchor context + article list + depth instructions. As more context is added, the risk of truncation or degraded output increases.

**Prompt-level decisions:**
- What is the priority order if the budget is tight? Suggested: anchor context > article headlines > article summaries > article full text > depth instructions. Never truncate the structure instructions.
- Should the system prompt contain a reminder to the model about what to do if it can't fit everything? ("If you cannot cover all articles in depth, prioritize the highest-severity ones.")
- For the cleaning pass: cleaned articles should be shorter than raw input. The cleaning prompt itself is a budget tool.

---

## 6. Background Churn and Session Memory

The concept: slow-changing content (YouTube transcripts, think tank reports, podcast transcripts from `data/context/` or fetched via diskcache) is periodically processed by the LLM to distill it into session-ready background knowledge. This is different from RAG injection — it's a separate "digest" pass that produces a summary suitable for context injection.

**Prompts to design:**
- **Churn prompt:** Takes a long-form document (transcript, report) and produces a condensed "analytical brief" — a 300–500 word summary in the analyst's voice, suitable for injecting as context into future briefings. Not a summarization prompt — it should extract *geopolitically relevant* content, identify the analyst's key claims and frameworks, and flag where they diverge from mainstream consensus.
- **Session background prompt:** At session start (or when the scheduler runs), assembles the most relevant churned summaries into a "background context" block that gets prepended to the system context for that session.

**Draft churn prompt:**
```
You are a geopolitical intelligence analyst preparing background context for an AI analyst session. Read the following content and produce a condensed analytical brief (300-500 words) covering:
- The main geopolitical claims or arguments made
- Any frameworks, historical references, or analytical lenses the author uses
- Where this analysis agrees with or diverges from mainstream Western/NATO consensus
- Any specific predictions, watch indicators, or scenarios raised

Be precise and attribute claims to the source. Do not add your own analysis — only extract what is present.

SOURCE: {source_name} ({source_type})
CONTENT:
{content}
```

---

## 7. Prompts Tied to TODO.md Features

These are prompting challenges associated with planned programming features. Writing the prompt is a separate task from implementing the code. Cross-reference numbers are from `TODO.md`.

### Event clustering (TODO #: Event-based briefing)
If approach A (LLM-based clustering) is chosen:
- Design a clustering prompt that takes N article titles/summaries and returns event groups with article IDs per group.
- The output format must be machine-parseable: JSON or a simple delimiter scheme.
- Key risk: the model may create too many or too few clusters. Need a max-cluster constraint in the prompt ("return no more than 8 event groups").

### AI-powered triage (TODO #: AI-powered triage)
- Replace keyword `score_severity` with an LLM triage call.
- Prompt must return only a number 1–5 on the first line. Nothing else.
- Consider a one-shot example in the prompt to anchor the scale.
- The 5 severity threshold in the current briefing template is explicit ("Reserve 5 ONLY for events that directly threaten large-scale loss of life...") — that same calibration needs to be in the triage prompt.

**Draft:**
```
You are a geopolitical severity triage system. Rate the severity of the following news item on a scale of 1-5:
1 = Routine diplomatic or political news. No immediate impact.
2 = Noteworthy development. Limited impact, no active escalation.
3 = Significant event. Active tensions, policy responses, moderate disruption.
4 = High severity. Military action, major sanctions, multi-state crisis.
5 = Critical. Direct large-scale loss of life, WMD use, or existential crisis affecting large populations. Reserve strictly.

Reply with a single digit only. No explanation.

TITLE: {title}
SUMMARY: {summary}
```

### Political leaning feature (TODO #: political leaning)
This is primarily a prompting challenge, not a programming one:
- What does "lean left" or "lean right" mean in a geopolitical briefing? It's not obvious.
- The stated intent is: override user's bias by showing them the consequences and historical framing that their preferred frame tends to suppress.
- A left-leaning user who wants validation of interventionism should get the realist critique. A right-leaning user who wants nationalism validated should get the internationalist critique.
- This needs careful prompt design to avoid being preachy or counterproductive. Framing it as "additional context" rather than "correction" may be more effective.
- **The Geopulse_constitution.md framing (consensus labeling, not truth-claiming) is the right foundation** for this feature — it already asks the model to name the frame rather than argue for it.

### "Where can I follow this closely?" (TODO #: Where can I follow)
- The chat system prompt needs enrichment so the model responds with concrete, named sources (X handles, YouTube channels, live streams, journalists).
- The model should not just say "follow Reuters" — it should name specific analysts, OSINT accounts, or commentators relevant to the specific story in the briefing.
- Consider injecting the briefing's topics and headline into the chat system prompt as context when this question is detected.

### Story update delta prompt (TODO #: Story update tracking)
- The existing `update_briefing_template` is a starting point but is minimal.
- The delta prompt should explicitly say: "What is NEW here that was NOT in the original briefing? Do not repeat what was already known."
- The tone should match the original briefing's depth level (brief update = 2-3 sentences; extended update = 1-2 paragraphs).

### Digest / "What did I miss" (TODO #: "What did I miss")
- Takes a list of briefings generated since last session and produces a single catch-up card.
- Should not just summarize each briefing — it should identify threads, escalations, and connections across them.
- "What has changed in the overall picture since you were last here?" is the question to answer.

---

## 8. Prompt Quality and Calibration (Ongoing)

- **Model-specific calibration:** The current prompts were developed and tested primarily on Qwen3:8b. Behavior on Mistral, Llama 3, Gemma, and cloud models (GPT-4o, Claude Sonnet) will differ. Maintain a note in `MODELS.md` on which prompts work well or badly per model.
- **Severity inflation:** The model tends to over-score severity. The explicit "Reserve 5 ONLY for..." instruction helps but may need reinforcing with examples (few-shot).
- **Marker compliance:** Some smaller models ignore the `<<<END>>>` marker and keep generating. The parser handles this but it wastes tokens. Consider adding "Stop immediately after `<<<END>>>`" to the template.
- **Language drift:** The model occasionally slips into less precise language under long context. Worth testing whether a brief reminder at the end of a long prompt ("Maintain analytical precision; avoid speculation") helps.
- **Citation quality:** The current prompt asks the model to "cite the sources you draw from" but doesn't enforce a citation format. Articles don't have clean bylines in the current pipeline. Consider adding source name + publication date to each article block in the prompt.

---

## 9. Geopulse_constitution.md Maintenance

The constitution is a living document. Planned additions:

- [ ] Monroe Doctrine / Latin American sovereignty anchor
- [ ] African decolonization / Berlin Conference anchor (currently abbreviated)
- [ ] Cold War proxy legacy anchor (applies globally to many current conflicts)
- [ ] Ottoman dissolution: expand the Abbreviated section into a full context file
- [ ] Add section: how the analyst should handle **AI training data bias** — acknowledge that training data skews anglophone and elite-media; flag explicitly when no regional sources are available
- [ ] Add section: **the multipolar transition** — framing the current moment as a contested shift from US-led unipolarity; the Global South's strategic autonomy; BRICS+ as a loose counter-alignment rather than a bloc
