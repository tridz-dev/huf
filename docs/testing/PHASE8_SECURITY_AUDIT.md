# Phase 8 Security Audit — P0.13 / P0.14

Verifies the current (`develop`-tracking, this branch) state of the 6 findings
that PR #304 ("security: implement obvious fixes from round-2 security
plans") explicitly deferred, per its own PR body and per `PR359_SALVAGE.md`'s
cross-referenced table. Source of the original findings: PR #303 (docs-only
plans, `doc/security-improvement-plans-2.md`, plans 008/010/011/012/014/015).

Every verdict below was checked against code that exists right now in this
worktree, not re-cited from the old PR description. Where practical, a
proof-of-concept was executed against the live `regression-safety-e2e.local`
bench (reachable at `http://127.0.0.1:8089` inside the
`frappe_docker_devcontainer-frappe-1` container) via
`bench --site regression-safety-e2e.local console`.

## Headline finding

**One of the six deferred findings is CONFIRMED STILL OPEN and exploitable
today: `huf.ai.audio_api.transcribe()` performs no permission check on the
`file_id` it is given.** Any authenticated user (no special role beyond
baseline `Huf User`) can pass an arbitrary `File` document name — including a
private file they do not own and cannot read via ordinary Frappe permissions
— and the file's bytes will be read from disk and forwarded to whichever STT
provider the chosen agent uses. This is a real arbitrary-file-disclosure
primitive (finding "transcribe_audio arbitrary File read" / Plan 011),
confirmed live against the bench, not a theoretical read of the old PR
description. See the P0.13 table, item 3, for the reproduction.

A second finding (JSX preview arbitrary JS execution, Plan 015) is also
confirmed still open by direct code inspection — `react-jsx-parser` still
evaluates expressions via `new Function` in the parent origin — but time did
not permit constructing a browser-side proof-of-concept; see item 6.

## P0.13 — Verdicts on the 6 findings deferred by PR #304

| # | Finding (PR #303 plan) | Verdict | Evidence | Severity if open |
|---|---|---|---|---|
| 1 | Conversation-mutation API authz (Plan 008) | **PARTIALLY FIXED** (the specific case the finding named is closed; see notes) | `huf/ai/agent_chat.py:293-298` (`get_history`) and `huf/ai/agent_chat.py:1093-1097` (`add_message`) both now check `conv_doc.owner != frappe.session.user and "System Manager" not in frappe.get_roles()` and raise `frappe.PermissionError`. `send_message_to_conversation` (`huf/ai/agent_chat.py:493`) itself still has **no** access check, but it delegates to `run_agent_sync` → `ConversationManager.get_or_create_conversation` (`huf/ai/conversation_manager.py:379-396`), which independently enforces `conversation.owner == frappe.session.user or conversation.session_id == self.session_id or has_capability(..., "chat.view_all")` before returning an existing conversation by id. Live PoC (two real users, one "Huf User"-role each) confirmed: attacker calling `send_message_to_conversation(conversation=<owner's conv>, ...)` gets `frappe.PermissionError: Conversation not found or access denied.` `api_set_conversation_data`/`api_get_conversation_data` in `huf/ai/conversation_data_tools.py:159-203` also gate on `frappe.has_permission("Agent Conversation", "read"/"write", conversation_id)`. | n/a — closed |
| 2 | Huf Data Table capability bypass (Plan 010) | **FIXED** | `huf/huf/doctype/huf_data_table/api.py`: a `data.tables.manage` capability now exists (`huf/permissions.py`), and all three mutation entry points call `_require_data_manage()` at their top: `create_data_table` (api.py:147, right after the docstring at line 136), `update_data_table` (api.py:231, `_require_data_manage()` at line ~239), `delete_data_table` (api.py:279, `_require_data_manage()` immediately inside). `_require_data_manage()` (api.py:41-46) throws `frappe.PermissionError` if `has_capability(frappe.session.user, "data.tables.manage")` is false. | n/a — closed |
| 3 | `transcribe_audio` arbitrary File read (Plan 011) | **STILL OPEN — CONFIRMED EXPLOITABLE** | `huf/ai/audio_api.py:22-98` (`transcribe`, `@frappe.whitelist()`) accepts a caller-supplied `file_id` and passes it straight to `huf/ai/audio_service.py:transcribe_audio_file()` (line 472) → `_resolve_file_doc(file_id=file_id)` (line 456-469) → `frappe.get_doc("File", file_id)`. **No `frappe.has_permission("File", "read", ...)` call and no ownership/attachment check exist anywhere on this path.** Live PoC: created a `poc_owner@example.com` user, uploaded a `is_private=1` File; verified `frappe.has_permission("File","read",...)` as `poc_attacker@example.com` returns `False`; called the whitelisted `transcribe(file_id=<owner's private file>, agent=<any agent>)` as the attacker — it did **not** raise `PermissionError`, it proceeded past file resolution (`file_doc.get_full_path()` succeeded) and only failed downstream because the test agent had no STT model configured (`"No transcription model available for provider..."`). With a real STT-capable agent configured, the private file's bytes would be sent to the external STT provider and the transcript returned to the attacker. | **HIGH** — unauthenticated-within-tenant arbitrary file read/exfiltration via a whitelisted endpoint; affects any `File` doc regardless of `is_private`, owner, or `attached_to_doctype`. |
| 4 | TTS/STT keys in `os.environ` (Plan 012) | **FIXED** | `rg -n "os\.environ\[" huf/ai/*.py` → zero matches anywhere in `huf/ai/`. The `_TTS_ENV_VAR_PROVIDERS` mapping and all `os.environ[...] = api_key` assignments described in the original finding are gone; API keys are passed as explicit `api_key=` kwargs to litellm calls. | n/a — closed |
| 5 | HTML/SVG same-origin artifact execution (Plan 014) | **FIXED** | `frontend/src/components/chat/ArtifactRenderer.tsx:215-245`: both the `'html'` case (line ~220) and the `'svg'` case (line ~238) render via `<iframe srcDoc={...} sandbox="">` — empty sandbox, no `allow-scripts`, no `allow-same-origin`. The SVG path no longer uses `dangerouslySetInnerHTML`. | n/a — closed |
| 6 | JSX preview arbitrary JS execution (Plan 015) | **STILL OPEN** (confirmed by code inspection; not live-exploited) | `frontend/src/components/ui/jsx-preview.tsx:24` imports `react-jsx-parser`; `defaultBindings` (lines 330-382) exposes `Math`, `JSON`, `Array`, `Object`, `console` directly to JSX expressions, and the component (line ~495) renders with no iframe, no sandbox, and no `allow-same-origin` removal — because there is no iframe at all. `react-jsx-parser` evaluates inline `{...}` expressions via `new Function(...)`, which executes in the parent page's global scope regardless of what is or isn't listed in `bindings` (bindings only add named locals; they do not remove `window`/`document`/`fetch` from the enclosing scope) — this is documented, well-known behavior of the library, not a hypothesis about this codebase. A malicious/compromised agent that can get JSX artifact content rendered in a user's chat (e.g. via a poisoned tool result or an untrusted knowledge-source excerpt echoed back as a JSX artifact) can execute arbitrary JS with the viewing user's cookies/session/localStorage. | **HIGH** — same class of primitive PR #303 flagged (stored XSS / origin escape in chat artifact rendering); no additional mitigation has landed since PR #304 deferred it. |

Note on item 1: the original Plan 008 also named `upload_audio_and_transcribe_web` as in-scope. That function (`huf/ai/agent_chat.py:138`) still does `frappe.get_doc("Agent Conversation", conversation)` with **no owner/session check** before inserting an `Agent Message` into it — but because it only reaches an *existing* conversation when the caller passes one they already know the id of, and it doesn't route through `get_or_create_conversation`'s check, this remains a narrower unaddressed gap in the same family as Plan 008. It was not re-tested live (would require an STT-capable agent and file upload) but the code path shows no access-control call at all, unlike its sibling `send_message_to_conversation`. Flagging this for the same follow-up that would harden `transcribe`/JSX preview, since it is the same missing-authz pattern, just not the specific instance the original finding named.

## P0.14a — `huf/ai/flow_eval.py` (AST-based expression evaluator)

**What it allows:** dict/list subscript access (`context["key"]`, including
nested), comparisons (`==`, `!=`, `<`, `<=`, `>`, `>=`, `in`, `not in`, `is`,
`is not`), boolean `and`/`or`/`not`, arithmetic `+ - * %`, unary `-`/`+`,
ternary `a if b else c`, and literal `list`/`dict`/`tuple`/constant syntax.
Everything is dispatched through a hand-written recursive `_eval_node()` over
`ast.parse(expr, mode="eval")` (`huf/ai/flow_eval.py:80,93-225`).

**What it rejects, and why it holds up:**
- `ast.Call` is unconditionally rejected (`flow_eval.py:216-220`) — this alone
  blocks every classic sandbox escape that needs a function call:
  `__import__(...)`, `getattr(...)`, `eval(...)`, `exec(...)`,
  `().__class__.__bases__[0].__subclasses__()` (that chain also needs
  `.__subclasses__()` to be *called*).
- `ast.Attribute` is unconditionally rejected (`flow_eval.py:209-213`) — this
  independently blocks the same escape chain even before the `Call` check
  would matter, since `x.__class__`, `x.__globals__`, `x.__builtins__` all
  require attribute access.
- `ast.Name` resolution only recognizes the literal binding `context`
  (`flow_eval.py:101-107`) — `os`, `__builtins__`, and any other bare name
  throw `"Unknown variable"` before ever reaching Python's real
  name-resolution machinery.
- Statements (`import`, assignment) are not expressible at all —
  `ast.parse(mode="eval")` itself raises `SyntaxError` on them, caught and
  re-raised as `frappe.ValidationError` (`flow_eval.py:79-82`).
- Subscript is restricted to `dict`/`list` targets only (`flow_eval.py:117-121`)
  — you cannot subscript a string or other object to reach `__getitem__`
  tricks.
- Comprehensions and lambdas are not handled by any branch, so they fall
  through to the final generic `"Unsupported expression element"` throw
  (`flow_eval.py:222-225`).

**No sandbox-escape vector found.** The evaluator is a strict allow-list
walker (every AST node type must be explicitly handled or it throws), not a
deny-list, which is the right shape for this kind of sandbox and is why the
classic dunder-chain escapes don't apply here.

**Minor, non-exploit finding worth flagging:** `ast.Mult` is in `SAFE_OPS`
(`flow_eval.py:30`) and works on `str * int` via `operator.mul`, same as
native Python. A context value that is attacker-influenced (e.g. `"a" * 999`
if `999` fits in the 500-char expression cap) could produce a large string,
but the 500-char `MAX_EXPRESSION_LENGTH` cap (`flow_eval.py:37,73-77`) limits
how large a literal multiplier can be typed inline; this is a low-severity,
theoretical DoS surface, not a confirmed exploit, and not worth a dedicated
fix at this time.

**Tests written:** `huf/ai/tests/test_flow_eval_security.py` — 19 tests,
pure `unittest`, no bench/site DB required (only `frappe` itself is
imported, for `frappe.ValidationError`), covering:
- 7 "intended-safe" cases (equality, nested dict access, `and`/`or`/`not`,
  comparisons + arithmetic, `in`/`not in`, ternary, missing-key-returns-None).
- 12 escape/rejection cases: `__import__` + call, bare function calls,
  attribute access (including the classic `().__class__` /
  `context.__class__` chain), `getattr`, lambda, `exec`/`eval`, unknown
  names (`os.system`, `__builtins__`), unparseable `import` statement,
  assignment, comprehensions, subscripting a non-dict/list, and the
  expression-length cap.

**Execution result (real, via
`bench --site regression-safety-e2e.local run-tests --app huf --module huf.ai.tests.test_flow_eval_security`):**

```
...................
----------------------------------------------------------------------
Ran 19 tests in 0.040s

OK
```

`python3 -m py_compile huf/ai/tests/test_flow_eval_security.py` also passes
cleanly (no syntax errors).

## P0.14b — Orchestration plan-priority/scheduler risk assessment

Files: `huf/ai/orchestration/orchestrator.py`, `huf/ai/orchestration/scheduler.py`,
`huf/ai/orchestration/planning.py`. Not full test coverage (out of scope for
this task) — a short, concrete risk list for a follow-up task to pick up.

1. **Missing authorization on `recreate_orchestration_plan`
   (`huf/ai/orchestration/orchestrator.py:71-96`, `@frappe.whitelist()`).**
   It takes a caller-supplied `orch_name`, loads *any* `Agent Orchestration`
   document with no ownership/permission check at all (contrast with the
   sibling `stop_orchestration` at line 118-134, which does check
   `frappe.has_permission("Agent Orchestration", "write")` before acting), and
   triggers a fresh LLM planning call (`run_planning`, an actual model
   invocation) against that orchestration's agent, then overwrites its
   `agent_orchestration_plan` child table and flips status back to
   `"Running"`. Any authenticated user who can call whitelisted methods can
   invoke this against orchestrations they do not own: unauthorized plan
   mutation, plus cost/quota abuse via forced LLM calls on someone else's
   orchestration. This is the same missing-authz pattern documented and
   fixed elsewhere in this codebase (Plan 008's `_assert_conversation_access`
   idea) but never applied here. **Recommend adding a
   `frappe.has_permission("Agent Orchestration", "write", orch_name)` (or an
   owner check) at the top of `recreate_orchestration_plan`, mirroring
   `stop_orchestration`.**

2. **Unbounded step count / cost multiplication.** `create_orchestration`
   (`orchestrator.py:10-69`) builds the step list either from a caller-
   supplied `override_plan` list, an `Agent.default_plan` child table, or raw
   LLM output parsed by `parse_plan_steps` (`orchestrator.py:98-116`, a naive
   numbered-line splitter with no bound). There is no maximum step count
   enforced anywhere in this file. `scheduler.py:process_orchestrations()`
   (called every minute via the Frappe scheduler) will keep enqueueing
   `execute_next_step` for every orchestration in `Planned`/`Running` status
   until all steps are `done`/`failed`, each step being a full
   `run_agent_sync(..., now=True)` LLM call (`orchestrator.py:184-194`). A
   maliciously large `override_plan` (if any caller path can reach it with
   attacker-controlled input) or a prompt-injected planning LLM response that
   produces hundreds of numbered "steps" would silently multiply real LLM
   spend with no cap and no operator alert short of the existing 900s
   per-step timeout (`scheduler.py:7,36`). **Recommend a hard cap (e.g. 20-50
   steps) enforced in `create_orchestration`/`recreate_orchestration_plan`
   before the plan is persisted.**

3. **Direct/inline execution (`now=True`) from a background worker context.**
   `execute_next_step` (`orchestrator.py:136-222`) is invoked via
   `frappe.enqueue(...)` from the scheduler (`scheduler.py:54-60`) — i.e. it
   already runs in an RQ worker — and then itself calls
   `run_agent_sync(..., now=True)` (`orchestrator.py:184-194`), which per this
   repo's own documented pitfall (`CLAUDE.md` under "Queue-first execution":
   *"Never call the direct path (now=1) from code that may hold or contend
   with the conversation lock ... it deadlocks"*) is exactly the pattern to
   avoid when a conversation is attached (`orch.conversation` is passed
   through as `conversation_id` at `orchestrator.py:192`). If two
   orchestration steps (or an orchestration step and a concurrent normal chat
   turn) ever contend for the same conversation's lock while one of them is
   already inside a worker holding it, this is a documented deadlock
   pattern, not a new discovery — but it does not appear to have been
   re-verified against the *current* orchestration code specifically.
   **Recommend a dedicated concurrency test: two orchestration steps or an
   orchestration step racing a normal chat message against the same
   `orch.conversation`.**

No arbitrary-code-execution vector was found in the orchestration plan data
itself — `next_step.instruction` and `orch.scratchpad` are treated as plain
text prompts fed to `run_agent_sync`, not evaluated as code, and the plan
step list is a plain Frappe child table (structured data), not something
`eval`'d. The risk here is authorization and resource-exhaustion, not code
injection.

## Files touched

- `docs/testing/PHASE8_SECURITY_AUDIT.md` (this file, new)
- `huf/ai/tests/test_flow_eval_security.py` (new, 19 passing tests)
