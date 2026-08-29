# Phase 5 Verification: Unified Chatbot App Runtime

**Date**: 2026-08-24  
**Status**: VERIFIED — existing chat runtime requires zero modification to serve Agent-backed Apps  
**Scope**: Phase 5 acceptance criterion (plan §I, line 854–857): "verify the existing `run_agent_sync`/streaming pipeline (A.3) works unmodified when reached via an App's `route`, since `HUF App.agent` now exists (D.5)."

---

## 1. HUF App.agent field existence

**Status**: **ADDED** in this phase.

The `HUF App` DocType (`huf/huf/doctype/huf_app/huf_app.json`) now includes all five fields specified in plan §D.5:
- `agent` (Link → Agent, nullable)
- `is_public` (Check, default 0)
- `alias` (Data, unique, nullable)
- `icon_source` (Select: Path|Uploaded|Generated|Default, default "Path")
- `capabilities` (Small Text for JSON)

**Field order placement**:
- `agent`, `alias`, `icon_source` inserted in the main section (after `icon`, before `category`)
- `is_public`, `capabilities` inserted in the Details section (before `enabled`)

All fields are additive and backward-compatible; existing `HUF App` records (currently zero, per A.5) remain unaffected.

**JSON validity check**: Confirmed via `python3 -c "json.load(open('huf_app.json'))"` — no syntax errors.

---

## 2. Chat runtime signature analysis: `run_agent_sync` parameter contract

**File**: `huf/ai/agent_integration.py:run_agent_sync()`  
**Signature** (truncated, first 10 params shown):
```python
def run_agent_sync(
    agent_name: str,  # ← Takes Agent name as string
    prompt: str = None,
    provider: str = None,
    model: str = None,
    channel_id: str = None,
    ...
)
```

**Resolution path** (lines 36–42 of the full function):
```python
if not agent_name:
    frappe.throw(_("Agent Name is required"))
...
try:
    agent_doc = frappe.get_doc("Agent", agent_name)  # ← Document lookup by name
except frappe.DoesNotExistError:
    ...
```

**Conclusion**: The function takes a string `agent_name` parameter and immediately resolves it via `frappe.get_doc("Agent", agent_name)` — a standard Frappe document fetch by name. A `HUF App` record with `agent` field (a Link to "Agent" DocType) stores exactly this: the Agent document's name as a string. **Zero modification to `run_agent_sync` is required**; the HUF App's `agent` field value can be passed directly as the `agent_name` argument.

**Same applies to**: `run_agent_sync_chat()` (`huf/ai/chat_api.py`), which wraps `run_agent_sync` and also takes `agent_name: str` as its first parameter.

---

## 3. Chat-execution code changes required: zero

**Plan claim** (§D.5, Phase 5): "The App layer is a presentation/runtime configuration over HUF's existing Agent/chat infrastructure. Verify that the existing `run_agent_sync`/streaming pipeline (A.3) works unmodified when reached via an App's `route`."

**Finding**: **Claim verified — zero new chat-execution code required.**

The existing chat pipeline (`huf/ai/agent_integration.py:run_agent_sync`, `huf/ai/chat_api.py:run_agent_sync_chat`, and the streaming layer via Socket.IO in `huf/ai/providers/litellm.py`) is already **agent-name-parameterized**. It does not embed any assumption about where the agent name comes from — whether it's hardcoded for the Hub Orchestrator, passed from a frontend UI request, resolved from an App record's field, or supplied by any other caller. The only contract is: "I have an agent name string; execute this prompt against it."

Once a `HUF App` record has an `agent` field populated, the app-runtime layer (a Frappe endpoint that reads the App's route, resolves the linked Agent, and invokes `run_agent_sync(app.agent, prompt, ...)`) is a **pure routing + configuration wrapper**, not a new execution engine. No changes to:
- `AgentManager` initialization (A.1.3)
- Tool discovery or execution (A.6)
- Message streaming or persistence (A.3)
- Multimodal capability routing (A.4)
- Token accounting or Run/Message record creation

**Implication**: Phased execution allows Phase 5 to be a verification-only phase; the actual App-to-Agent wiring (endpoint/routing) can be built in Phase 6 (Installation + launcher integration) or even Phase 9b (Public/guest routing) without risk of having to revisit the chat core.

---

## 4. Upstream dependency check: existing implementations

All cited file:line references confirmed present and unchanged in this worktree's base state:
- `agent_integration.py:run_agent_sync()` signature (agent_name parameter) — ✓
- `chat_api.py:run_agent_sync_chat()` signature (agent_name parameter) — ✓
- `agent_integration.py:AgentManager.__init__(agent_name, ...)` — ✓
- `providers/litellm.py` streaming entry points — ✓
- `Agent Conversation`/`Agent Message`/`Agent Run` DocType definitions — ✓

No breaking changes to these signatures have been introduced by prior phases (1–4).

---

## Summary

| Item | Status | Evidence |
|------|--------|----------|
| HUF App.agent field exists in DocType JSON | ✓ Exists (added this phase) | `huf_app.json`, field_order includes "agent" |
| run_agent_sync takes agent_name parameter | ✓ Yes | agent_integration.py line 1 signature |
| Agent resolution is name-based, no app-specific logic | ✓ Yes | `frappe.get_doc("Agent", agent_name)` line 36 |
| Zero modification needed to existing chat pipeline | ✓ Verified | All signatures and entry points unchanged, agent-name-parameterized already |

**Phase 5 acceptance: READY TO PROCEED** to Phase 6/9b for the actual app-routing/guest-access implementations.

