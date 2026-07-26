# Hub Simple — First-Run / Time-to-Value Audit

**Scope:** first-time user journey from fresh install to the first useful AI reply on the new hub (`/` → `HubSimplePage`). Static code audit only; no runtime execution. Personas: P1 = non-technical business user; P2 = ERP/Frappe functional consultant (no code).

---

## A1. First-run sequence

### What the installer seeds

`huf/install.py:after_install()` seeds the following on a fresh install (`huf/install.py:63-77`):

- **Huf Roles** (`create_huf_roles`): Huf Admin / Manager / User / Viewer and backing Frappe roles (`huf/install.py:588-667`).
- **AI Provider skeletons** (`create_demo_ai_providers`): OpenAI, Anthropic, Google, OpenRouter, xAI, Groq, DeepSeek, HuggingFace, Cohere, Perplexity, ElevenLabs — all with `api_key: ""` (`huf/install.py:161-191`).
- **AI Models** (`create_demo_ai_models`): ~70 models linked to those providers (`huf/install.py:193-275`).
- **System tools**: `generate_image`, `transcribe_audio`, `generate_audio`, `ocr_document`, flow tools (`huf/install.py:277-762`).
- **Integration services**: Slack, Discord, Telegram, GitHub, Jira, Gmail, Calendar, Drive, Sheets, Maps, Meet (`huf/install.py:778-914`).
- **Discovered tools** from app hooks (`huf/install.py:75-76`).

**Crucially, it does NOT seed a working agent.** The `huf/ai/app_seeding` machinery exists, but `scanner.py:13` explicitly skips the `huf` app itself, so `huf/huf/agents/demo-assistant.json` is never loaded. That seed is also `disabled: 1` (`huf/huf/agents/demo-assistant.json:12`).

### Journey from login to first reply

1. **Login** → Frappe redirects to the app home `/huf` (`frontend/src/App.tsx:81-89`).
2. **Hub loads** (`HubSimplePage.tsx:59`). It calls `getMe()` for role/capabilities and `getProviders({ limit: 1 })` (`HubSimplePage.tsx:98-103`).
3. Because seeded providers exist (even with empty API keys), `hasProvider` becomes `true`. The composer is enabled. The user sees a role-based greeting:
   - Admin: *“What would you like to orchestrate?”* (`HubSimplePage.tsx:24`)
   - Builder/User: *“What are you building today?”*
   - Viewer: *“What insights are you looking for?”*
4. User types and sends. `sendToAgent()` calls `sendMessage({ agent: 'Hub Orchestrator', ... })` (`HubSimplePage.tsx:126-127`).
5. Backend `huf.ai.agent_chat.new_conversation` calls `run_agent_sync(agent_name='Hub Orchestrator', ...)` (`huf/ai/agent_chat.py:370-405`).
6. `run_agent_sync` does `frappe.get_doc("Agent", "Hub Orchestrator")` (`huf/ai/agent_integration.py:660`) → `DoesNotExistError`.
7. Frontend catches the error and renders: *“Hub Orchestrator agent is not configured yet. Go to Agents to set one up.”* (`HubSimplePage.tsx:138`).
8. User navigates to **Agents** (`/agents`). The page is empty because no agent exists. User clicks Add/Create Agent.
9. **Agent form** requires: Agent Name, Provider (link to AI Provider), Model (link to AI Model). The user can pick the seeded OpenAI provider and `gpt-4o-mini` model and save.
10. Back on the hub, user sends again. Now `AgentManager._setup_client()` calls `get_password("api_key")` and finds an empty key (`huf/ai/agent_integration.py:95-97`) → `frappe.throw("API key is not configured in AI Provider.")`.
11. The frontend catch still shows the same generic message: *“Hub Orchestrator agent is not configured yet...”* (`HubSimplePage.tsx:138`). Nothing tells the user the problem is the missing API key.
12. User eventually discovers **AI Providers** (`/models` from sidebar, or `/providers`). Opens the OpenAI card, enters an API key, saves.
13. Returns to hub, sends again. If the key is valid and the model name resolves through LiteLLM, the first real reply arrives.

### Step count to first value

Minimum distinct interactions:

1. Log in.
2. Read hub greeting.
3. Type first message and send.
4. Read error → realize an agent is missing.
5. Navigate to Agents.
6. Click Add Agent.
7. Fill Agent Name = "Hub Orchestrator".
8. Select Provider.
9. Select Model.
10. Save agent.
11. Return to hub, send again.
12. Read the same generic error → realize API key is missing.
13. Navigate to AI Providers.
14. Find provider, click Configure.
15. Paste API key.
16. Save provider.
17. Return to hub, send again.
18. Receive first reply.

**~18 steps**, with two confusing error loops where the same message masks two different root causes.

### First moment of value

The first moment of value is the LLM reply in step 18. Everything before it is configuration. The hub UI promises value immediately (*“Ask anything or type / for commands...”*, `HubSimplePage.tsx:304`), but cannot deliver until the user has manually created an agent and supplied a real API key.

---

## A2. Blocking walls

| Wall | What the user sees | Root cause | Would P1/P2 know what to do? |
|---|---|---|---|
| **No provider** (only if all provider docs deleted) | Amber card: *“No AI Provider configured”*, *“Add a provider and model to start using Hub Orchestrator.”*, button *“Add Provider →”* (`HubConversationView.tsx:77-82`). | `hasProvider === false` triggers a 300 ms fake reply containing `__NO_PROVIDER__`, rendered as the card. | Partially. “AI Provider” and “Orchestrator” are jargon, but the button is a clear call-to-action. Confusingly, the link goes to `/huf/models` (the Models page), not `/providers`. |
| **Provider exists but no API key** | Same generic error: *“Hub Orchestrator agent is not configured yet. Go to Agents to set one up.”* (`HubSimplePage.tsx:138`). | `AgentManager._setup_client()` throws `API key is not configured in AI Provider.` (`huf/ai/agent_integration.py:97`), but the frontend catch block maps every failure to the missing-agent copy. | **No.** The copy says the *agent* is missing, not the API key. P1/P2 will likely re-check the agent form repeatedly. |
| **No model** | `/models` empty state: *“No models found.”* (`frontend/src/pages/ModelsPage.tsx:331`). | Models are seeded, so this only appears if models are deleted; but a user who creates only a provider will still fail because the agent form requires a model. | A business user will not know what a “model” is in this context. |
| **No Hub Orchestrator agent** | *“Hub Orchestrator agent is not configured yet. Go to Agents to set one up.”* (`HubSimplePage.tsx:138`). | The hub hardcodes `agent: 'Hub Orchestrator'` (`HubSimplePage.tsx:127`) and no agent with that name is seeded. | P2 might create an agent, but must guess the exact name “Hub Orchestrator”. P1 will be lost until guided. |
| **Streaming unavailable** | Toast: *“Streaming not working”*, *“Some features may be disabled or not work as expected. Please refresh the page to retry.”* (`frontend/src/App.tsx:503-506`). | `/huf/stream/ping` check fails; `streamingAvailable` remains false. | Sounds technical (“streaming”, “SSE”). Not blocking because the code falls back to REST (`streamChatApi.ts:185` vs `252-262`). |

### Provider creation form friction

The **Add Provider** modal (`frontend/src/pages/AiProvidersPage.tsx:338-415`) shows:
- **Provider Name** * (required) — placeholder: *“Enter provider name (e.g., OpenAI, Anthropic)”*.
- **API Key** — label only, no required asterisk in the UI, but the DocType marks it `reqd: 1` (`huf/huf/doctype/ai_provider/ai_provider.json:30`). Leaving it blank produces a generic *“Failed to create provider”* toast.
- **Provider Brand** * (required) — a select with values like `openrouter`, `xai`, `groq`, `deepseek`, `perplexity`, `cohere`, `huggingface`, `elevenlabs`, `amazon-bedrock`, `alibaba`, `togetherai`, `lmstudio`, `fireworks-ai`, `cerebras`, `deepinfra`, `google-vertex` (`frontend/src/data/provider-brands.json`). These are vendor names, but a non-technical user may not recognize most of them.

There is **no “base URL” or “LiteLLM format” field** on the provider form itself; those concepts appear only in model help text and code.

### Model creation form friction

The **Add Model** modal (`frontend/src/pages/ModelsPage.tsx:397-578`) shows:
- **Model Name** * — placeholder *“Enter model name (e.g., gpt-4, claude-3)”*.
- **Provider** * — select from existing providers.
- **Modality** — options: Text, Image, Text-to-Speech, Transcription, Embeddings, Vision, OCR (`huf/huf/doctype/ai_model/ai_model.json:41`).
- Help text: *“Enable custom prices to override LiteLLM's automatic pricing lookup... Values are in USD per 1 million tokens.”* (`frontend/src/pages/ModelsPage.tsx:477-479`) and *“Cost in USD per 1 million prompt/input tokens”*.

No explanation of what “LiteLLM format” means or that model names are normalized automatically.

---

## A3. Jargon audit (first-run surfaces)

### Hub (`HubSimplePage.tsx`)

| String | Line | Issue |
|---|---|---|
| “What would you like to **orchestrate**?” | 24 | Technical verb; business users ask “do” or “help with”. |
| “**Hub Orchestrator**” | 72, 127, 138 | Product/system name presented as if the user should know it. |
| “**System**” badge | 73 | Suggests a system agent, but no explanation. |
| “**AI Providers**” sidebar label | 56 | Path is `/models`; “Providers” and “Models” are two different pages. |
| “Flows” / “Executions” / “Knowledge” | 53-55 | Domain terms; no onboarding hint. |
| Slash commands `/flow`, `/agent`, `/knowledge`, `/runs`, `/settings`, `/cost` | 161-164 | `/settings` routes to `/models` (wrong), `/cost` routes to `/` (unimplemented). |
| “Switch to Advanced Hub” | 238 | Implies the current view is “simple”, but no contrast is explained. |

### `/models` (ModelsPage.tsx) and model form

| String | Line | Issue |
|---|---|---|
| “Manage AI models and their capabilities” | 311 | “Capabilities” is vague. |
| “Modalities” | 455 | Technical ML term. Options include “Embeddings”, “OCR”, “Vision”, “Text-to-Speech”. |
| “LiteLLM's automatic pricing lookup” | 478 | Product name/jargon. |
| “Input Cost per **1M Tokens** (USD)” | 499 | “Tokens” is unexplained. |
| “Cached Input Cost per 1M Tokens” | 533 | “Cached input” / cache-read pricing is advanced. |

### `/providers` (AiProvidersPage.tsx) and provider form

| String | Line | Issue |
|---|---|---|
| “Connect AI providers and external services” | 251 | “AI provider” is acceptable to P2, less so to P1. |
| “API Key” | 373 | P1 may not know what an API key is or where to get one. |
| “Provider Brand” | 383 | Tied to a long list of vendor slugs. |
| “models” count badge | 290-291 | e.g. “3 models” under provider name. |

### Agent form (encountered after first error)

| Term | Source | Issue |
|---|---|---|
| “LLM Configuration” | `agent.json:427` | Acronym. |
| “Temperature” / “Top P” | `agent.json:218-251` | Sampling parameters; unexplained to non-technical users. |
| “MCP Servers” | `agent.json:234-244` | Acronym; no in-app explanation. |
| “Knowledge Sources” / RAG | `agent.json:311-322` | RAG is never spelled out. |
| “Context Strategy”, “Summarize”, “FIFO” | `agent.json:330-341` | Technical memory-window concepts. |
| “Prompt Caching” | `agent.json:484-523` | Advanced cost feature. |
| “Max Knowledge Tokens”, “Max Context Characters” | `agent.json:411-676` | Token/character budgeting jargon. |
| “DocType” | Tool descriptions throughout | Frappe-specific term; P1 will not know it. |

---

## A4. Defaults & safe paths

### Current defaults

- **Providers**: Seeded with no API keys. `hasProvider` is true, so the hub never shows the onboarding card even though no real provider is usable.
- **Models**: Seeded, but none is marked as default.
- **Agent Settings**: The `Agent Settings` singleton exists with `default_provider` and `default_model` links, but the installer does not populate them (`huf/huf/doctype/agent_settings/agent_settings.json:8-24`).
- **Demo agent**: Exists as `huf/huf/agents/demo-assistant.json` but is `disabled: 1` and not loaded because the scanner skips the `huf` app.
- **Hub agent**: There is no backend concept of a “hub agent”. The frontend hardcodes the string `Hub Orchestrator`.

### Shortest realistic path if defaults were fixed

With three minimal backend changes, the path could be:

1. **Seed an enabled system agent** named `Hub Orchestrator` (or resolve it via `Agent Settings.hub_agent`) linked to the default provider/model.
2. **Populate `Agent Settings`** with a default provider and model so the seeded agent has valid links.
3. **Prompt for an API key on first hub visit** if the default provider’s key is empty, instead of letting the user send into a generic error.

That would reduce the journey to:

1. Log in.
2. Hub greets user.
3. If API key missing, inline banner: “Paste your OpenAI API key to start chatting.”
4. Paste key.
5. Send message → immediate reply.

**~5 steps instead of ~18.**

---

## A5. Time-to-value estimate

### Assumptions

- Fresh install with seeds as described.
- User is Administrator (so they can create providers/agents; a Huf User/Viewer cannot create providers and would be blocked entirely).
- User has an API key available for at least one seeded provider (e.g., OpenAI).
- No one is guiding them; they rely on UI copy.

### Today

- **P1 (business user)**: **30–50 minutes** to first reply. Most time is lost decoding why the same error appears after creating the agent, realizing an API key is needed, and finding the provider configuration.
- **P2 (functional consultant)**: **15–30 minutes**. They understand Frappe forms and the provider/agent/model hierarchy, but they still hit the undifferentiated error and must manually create an agent with the magic name `Hub Orchestrator`.

### With the top 3 cheapest fixes

1. **Differentiated hub error handling** (distinguish missing agent vs. missing API key vs. provider/model misconfig).
2. **Seed an enabled Hub Orchestrator agent** linked to default provider/model, plus populate `Agent Settings` defaults.
3. **Inline API-key prompt** when the provider exists but has no key, instead of a generic “agent not configured” message.

Estimated TTV:

- **P1**: **5–10 minutes** (paste API key, send).
- **P2**: **3–5 minutes**.

---

## Verdict

**BLOCKED** for a first-time user. The hub UI is visually polished, but the first-run path is not merely bumpy—it fails on the first message and misdiagnoses the root cause. A non-technical user cannot reach a working AI answer without Frappe-admin-level knowledge and trial-and-error.
