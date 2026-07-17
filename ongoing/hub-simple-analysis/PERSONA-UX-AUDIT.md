# HUF — Business-User & Functional-Consultant UX Audit

**Personas:** P1 = normal business user (non-technical). P2 = functional consultant (ERP/Frappe-savvy, no code).
**Lenses:** ease of first use, time-to-value, intuitiveness.
**Scope:** branch `feat/design-simplified-hub-homepage-interface` @ `4a28794d` (Hub Simple + develop). Static code audit — copy, flows, defaults, required fields; not runtime-tested. Detailed evidence: `06a-first-run.md`, `06b-flows-intuitiveness.md` (file:line for every claim).

---

## Headline

**HUF today is a developer's product wearing a business-user home page.** The new hub promises "ask anything" but a fresh install fails on the very first message, and everything past the chat surface (agent form, tools, triggers, flows) speaks Frappe/LLM-engineer vocabulary. Verdicts from the two audits: first-run = **BLOCKED**, core flows = **EXPERT-ONLY**. The good news: the worst problems are concentrated, cheap to fix, and mostly seeding + copy + progressive disclosure — not architecture.

**Time-to-first-value today:** P1 ≈ 30–50 min, P2 ≈ 15–30 min (18-step journey with two misdiagnosed error loops). **With three cheap fixes:** P1 ≈ 5–10 min, P2 ≈ 3–5 min (5 steps).

---

## 1. First use: the broken golden path

The installer seeds 11 providers (all with **empty API keys**), ~70 models, tools, and integrations — but **no working agent**. The demo-assistant seed exists but is `disabled: 1` AND never loaded (the seeding scanner skips the `huf` app). So:

1. Hub greets the user ("What are you building today?") with an enabled composer — because empty-key providers make `hasProvider` true.
2. First message → `Agent "Hub Orchestrator"` doesn't exist → *"Hub Orchestrator agent is not configured yet. Go to Agents to set one up."*
3. User creates an agent (must **guess the magic name** "Hub Orchestrator"), sends again → now fails on the empty API key → **the exact same error message**. Nothing ever says "paste an API key."
4. Only after discovering AI Providers and pasting a key does step ~18 deliver the first reply.

This is the single most damaging finding: the product's first impression is a polished screen that lies about readiness, then misdiagnoses its own failure twice.

**Fix package (small, high leverage):**
- Seed an enabled, `is_system` Hub Orchestrator (the field and guards landed today; the seed + scanner un-skip is the remaining work), and populate `Agent Settings` default provider/model.
- Differentiate hub errors: missing agent ≠ missing API key ≠ provider error; each with its own CTA.
- First-visit readiness check: if the default provider has no key, show an inline "Paste your API key to start" banner and disable the composer — don't let users send into failure.

## 2. Time-to-value

| | Today | After fix package |
|---|---|---|
| P1 business user | 30–50 min, likely gives up at the second identical error | 5–10 min |
| P2 functional consultant | 15–30 min (knows Frappe forms, still trapped by the undifferentiated error + magic agent name) | 3–5 min |

Steps to first value: **~18 → ~5**. The delta is almost entirely seeding + error copy.

## 3. Intuitiveness by surface (best → worst)

- **Chat** — the most polished surface: markdown, artifacts, media, collapsible tool cards. Ship-quality for P1.
- **Executions / run detail** — mostly readable statuses, but: page says `Failed` and **never renders `error_message`** (P1 has no idea why), cost shows 6 decimal places, and "Agent Orchestration"/"Run ID"/"Executions" are log-file vocabulary.
- **Agent form** — P2 can make a working agent in 4 decisions (name, provider, model, instructions) since chat defaults are on. But nothing tells them the other ~30 options are ignorable: Temperature/Top P sliders with "nucleus sampling" prose, prompt caching, FIFO/summarize context strategy, token budgets — all flat-exposed. P1 is lost immediately. Also: `instructions` isn't required by validation, so users can save an agent that can't work.
- **Tools** — friendly template picker ("Read, create, update records from your database"), then a cliff: JSON schema previews, `Function Path` dotted-Python inputs, HTTP header JSON, `fieldname` parameter tables. P2 survives guided CRUD/HTTP; anything custom is developer-only.
- **Triggers** — raw Frappe hook names (`after_insert`, `on_submit`, `on_trash`) as user-facing options plus a "Condition (Python)" free-text field. This is P2's core job (automation on document events) expressed in backend vocabulary — the highest-value translation work in the product.
- **Flows** — plain-language node pickers (good), but branching requires typing `context["status"] == "approved"`, loops require Node IDs and context keys, unexplained "Agentic" mode and "Max Hops", and a raw-JSON fallback panel. Not no-code yet; P2 can build linear flows only.

## 4. IA & language

Navigation has a coherent Build/Operate skeleton, but leaks: **MCP Servers, Console, Executions, Models, Agent Summary Prompts** as top-level labels; "AI Providers" in the hub sidebar routes to `/models`; hub slash commands `/settings` and `/cost` route to a NotFound page and `/` respectively. A P1 asking "where do I make the AI answer invoice questions?" has no obviously right door — Chat needs an existing agent, Agents drops them into the jargon form, Knowledge is capability-gated.

Recurring jargon on first-run surfaces: orchestrate/orchestrator, API key, provider brand, modality, tokens, LiteLLM, MCP, RAG, DocType, temperature/top_p, FIFO, SSE/streaming.

## 5. Prioritized recommendations

**P0 — first-run (do before any launch to these personas):**
1. Seed the system Hub Orchestrator + Agent Settings defaults; un-skip huf in the seeding scanner.
2. Differentiated hub error copy with per-cause CTAs; readiness banner + disabled composer when the key is missing.
3. Fix or remove `/settings` and `/cost` slash commands; make "AI Providers" label and route agree.

**P1 — comprehension (cheap copy/disclosure work):**
4. Render `error_message` on failed run detail; round cost to 2–4 decimals; rename Executions → Run History (and audit the other dev labels: MCP Servers, Console).
5. Replace Temperature/Top P with a Precise/Balanced/Creative preset; move sliders + caching + context strategy behind an "Advanced" disclosure. Make `instructions` required.
6. Translate Doc Event triggers to plain language ("After a document is created/saved/submitted…") and replace the Python condition field with a field/operator/value builder (keep code mode as a toggle).

**P2 — builder depth (larger, schedule deliberately):**
7. Developer-view toggle on tool forms (guided fields default; JSON/function-path behind it).
8. Visual condition builder for flow edges/conditions; inline help for Agentic mode and Max Hops; approval-notification explanation on Human-in-Loop.

## 6. Open questions

1. Is P1 actually a launch target for the *builder* surfaces, or only for Hub + Chat (with P2 building)? The answer changes how much of P1–P2 above is launch-blocking vs. roadmap.
2. Should first-run offer a hosted/trial key path? Even a perfect flow still dead-ends P1 at "go get an OpenAI API key."
3. "Switch to Advanced Hub" implies a simple/advanced split — is that the intended progressive-disclosure strategy product-wide? If so, formalize it (per-role UI density) instead of per-form ad hoc toggles.

*All findings statically verified against code; no runtime walkthrough was performed. A follow-up moderated run-through on a seeded instance would validate the TTV estimates.*
