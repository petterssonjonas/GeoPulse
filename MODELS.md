# GeoPulse — LLM model compatibility and quality

This doc tracks which models **work** or **don’t work** for briefing generation, **why** they fail when they do, and how we **rate** their output. Use it to choose a model and to add new entries when you try one.

---

## Models known to work

Models that reliably produce parseable briefings (follow `<<<MARKERS>>>`, coherent text). Add rows as you verify.

| Model            | Provider | Notes / rating |
|------------------|----------|-----------------|
| **Qwen3:14b**    | Ollama   | Used in current runs; works. Produces structured briefings with markers. |

*Rating criteria (see below):* Markers present, headline/summary/developments non-empty, coherent prose.

---

## Models known not to work

Models that consistently produce empty or unparseable briefings, or that are unsuitable by design.

| Model               | Provider | Why it doesn’t work (detail) |
|---------------------|----------|------------------------------|
| **StarCoder2:15B**  | Ollama   | **Code-only model.** Trained for code completion, not instruction-following. Does not output `<<<MARKERS>>>` or structured prose; output is often code-like or fragmented. Briefing fields come back empty; fallbacks may produce a headline from article title but no real analysis. |

*When adding an entry:* Be specific — e.g. “never outputs markers”, “outputs markdown headers instead of <<<>>>”, “responses are one sentence”, “refuses the task”, “code snippets only”.

---

## Why some models don’t work (detail)

Reasons we’ve seen or expect; use these to fill the “Why it doesn’t work” column and to diagnose new models.

1. **Code-only / completion models**
   - Trained for code or generic completion, not chat or instructions. They may:
     - Ignore the system prompt and user format.
     - Output code, JSON fragments, or single-line completions instead of sections.
     - Never emit `<<<SECTION>>>` markers, so our parser gets nothing and fallbacks only give article-derived text.
   - *Examples:* StarCoder, CodeLlama (base), other “code” variants without “instruct” or “chat” in the name.

2. **Wrong output format**
   - Model follows the task but uses a different structure:
     - Markdown headers (`## Headline`, `## Summary`) instead of `<<<HEADLINE>>>` etc.
     - JSON instead of markers.
     - Single block of prose with no clear section boundaries.
   - Our parser is marker-based; without markers we only get content via fallbacks (first line, article titles). Quality is poor.

3. **Instruction-following too weak**
   - Model is chat/instruct but doesn’t reliably follow “EXACTLY this format”. It may:
     - Omit sections, merge sections, or add extra content that breaks boundaries.
     - Use slight marker variants (`### HEADLINE` or `[HEADLINE]`) we don’t parse.
   - Result: some fields empty, or wrong content in a field (e.g. summary in developments).

4. **Too short or too small**
   - Very small models may produce one-sentence answers or refuse. Briefings need multiple paragraphs and consistent structure; they fail or trigger fallbacks.

5. **Refusal / safety**
   - Some models refuse “intelligence briefing” style tasks or sanitize output heavily. We get empty or generic text.

6. **Language / tokenization**
   - Model optimized for non-English may produce broken or mixed language in sections, or odd formatting that breaks extraction.

When you see a new model failing, try to classify it into one of these (or add a new category) and document the exact behaviour (e.g. “outputs only <<<HEADLINE>>> then stops”, “repeats the instruction back”).

---

## Rating model work

We need a repeatable way to say how good a model’s briefings are (for choosing a default and for the “model database” in settings).

### Criteria (what to rate)

| Criterion              | What we check |
|------------------------|----------------|
| **Parseability**       | All required sections present and non-empty after parsing (headline, summary, developments). No need to rely on fallbacks. |
| **Format compliance**  | Uses `<<<MARKERS>>>` exactly; list sections (WATCH, QUESTIONS) parse as lists. |
| **Coherence**         | Summary and developments are readable, on-topic, and cite sources where asked. |
| **Depth**              | Extended depth: more paragraphs, nuance, competing interpretations. Brief depth: concise but complete. |
| **Stability**          | Same articles → similar structure and quality across runs; no random code or off-topic blocks. |

### How to rate (per run or per model)

- **Quick check (per run):** After generating a briefing, did it parse without fallbacks? Is the headline sensible and the summary/developments usable? If yes, note “works this run” and the model name.
- **Model-level:** After 3–5 runs with different article sets, decide:
  - **Works:** Consistently parseable and coherent; safe to recommend.
  - **Works with caveats:** Parseable but often needs fallbacks, or quality/depth inconsistent — note the caveat in the “Models known to work” table.
  - **Doesn’t work:** Consistently unparseable or unsuitable — add to “Models known not to work” with the detailed reason.

### Future: database and UI

Phase 0 / IMPLEMENTATION_ORDER call out a **database of models that work or don’t work** and a red indicator + message when a known-bad model is selected. That will consume this doc’s data (and/or a small `data/known_models.json` or DB table) so the app can warn without hardcoding.

---

## Changelog

- **2025-03-01:** Doc added. Qwen3:14b recorded as working. StarCoder2:15B recorded as not working (code-only). Rating criteria and “why models don’t work” sections added.
