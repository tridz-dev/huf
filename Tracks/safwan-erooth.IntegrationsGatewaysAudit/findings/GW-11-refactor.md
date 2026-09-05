# GW-11 refactor record: a shared "run an agent" identity/authorization helper

- Status: Accepted, implemented
- Date: 2026-09-05
- Track item: GW-11
- Scope: `huf/ai/agent_access.py` (new `resolve_run_identity_and_authorize` +
  `RunIdentityResult`), and the four call sites it now routes through:
  `huf/ai/agent_integration.py` (`run_agent_sync`), `huf/ai/gateway_service.py`
  (`process_gateway_event`), `huf/ai/flow_api.py` (`_run_flow_webhook`),
  `huf/ai/agent_hooks.py` (`run_agent_for_doc`). Plus a new test module,
  `huf/ai/tests/test_run_identity_authorization.py`.
- Builds on: GW-08 (`2c2e62ee`, `audit/integrations-gateways-clusterC`),
  cherry-picked onto this branch first (`63b33634`) so the gateway surface's
  post-GW-08 semantics (`check_agent_access(agent, gateway.execution_user)`,
  not Guest) are what this refactor preserves, not the pre-GW-08 behavior.

## What existed before this refactor

Four call sites, each independently deciding "who runs this, and are they
allowed to", with no shared code path and non-identical failure semantics:

1. **Direct API** — `agent_integration.py`'s `run_agent_sync`. Identity is
   `frappe.session.user` (no impersonation). After an earlier
   Guest-vs-agent-existence oracle-avoidance check, it called
   `assert_agent_access(agent_doc, user=frappe.session.user)` (which
   `frappe.throw`s `frappe.PermissionError` directly), then separately
   required the `agent.use` capability for any non-Guest user (raising a
   second, differently-worded `frappe.PermissionError` on its own).
2. **Gateway** — `gateway_service.py`'s `process_gateway_event`. Post-GW-08,
   identity is `gateway.execution_user`; the pre-gate called
   `check_agent_access(agent_doc, gateway.execution_user)` directly and, on
   failure, wrote a `Gateway Event` `status="Rejected"` /
   `error_message` naming `event.target_agent` — no exception raised.
3. **Flow webhook owner-impersonation** — `flow_api.py`'s
   `_run_flow_webhook`. Identity is `defn_doc.owner or "Administrator"`,
   applied via a bare `frappe.set_user(...)` with **no** per-Agent
   entitlement check at this layer (the webhook-key check already gates
   entry; a Flow, not one Agent, is the trigger target).
4. **Doc-event initiating-user replay** — `agent_hooks.py`'s
   `run_agent_for_doc`. Identity is `initiating_user` if it still exists,
   else silently the background worker's current session user (typically
   Administrator) — no log entry on that fallback. No entitlement check at
   this layer either; the downstream `run_agent_sync` call (site 1, above)
   is what actually authorizes the run, under whichever identity was
   resolved here.

Three of the four (1, 2, 4) ultimately rely on the exact same predicate,
`check_agent_access`, but called it from three different places with three
different argument-passing conventions, and surface 3 relies on none at all
by design. That divergence, not a single shared bug, is what GW-11 targets.

## The shared helper

`huf.ai.agent_access.resolve_run_identity_and_authorize(agent_doc,
trigger_surface, context) -> RunIdentityResult`, alongside four `TRIGGER_*`
string constants (`TRIGGER_DIRECT_API`, `TRIGGER_GATEWAY`,
`TRIGGER_FLOW_WEBHOOK`, `TRIGGER_DOC_EVENT`) and a `RunIdentityResult`
dataclass (`run_as_user`, `authorized`, `reason`, `fallback_applied`,
`fallback_reason`, `metadata`).

**Design choice: unify identity *resolution*, not failure *reporting*.** The
helper is a pure value resolver — it never calls `frappe.set_user`,
`frappe.throw`, or writes to any doctype. Each call site keeps deciding how
to surface an unauthorized result, because that shape is a genuine, correct
difference between the surfaces, not an accident: the direct API surface
must raise so the HTTP layer returns an error; the gateway surface must
persist a `Gateway Event` rejection so a webhook failure is diagnosable
after the fact (this is the same "failures must be legible" principle
GW-08's decision record and GW-09 both lean on). Collapsing that too would
have been forcing a bad abstraction, which the ticket explicitly warned
against. What is unified is the one part that was genuinely duplicated:
computing *who* runs the operation and whether `check_agent_access` admits
them.

**Per-surface behavior, exactly preserved:**

- `TRIGGER_DIRECT_API` (context: `{"user": ...}`, defaults to
  `frappe.session.user`): runs `check_agent_access(agent_doc, user)`, then —
  matching the original two-step check exactly — additionally requires
  `agent.use` for any non-Guest user. Two distinct rejection reasons are
  reproduced verbatim: `"You do not have access to run this agent."` (not
  entitled) and `"You are not authorized to use this agent."` (entitled but
  missing the capability). The call site still performs its own
  Guest/agent-existence oracle-avoidance check *before* calling the helper —
  that logic depends on the `None`-vs-real-`agent_doc` distinction and is
  left untouched, matching the ticket's "not a behavior change" instruction.
- `TRIGGER_GATEWAY` (context: `{"execution_user": ..., "target_agent": ...}`):
  runs `check_agent_access(agent_doc, execution_user)` — the post-GW-08
  predicate — and on failure reproduces the exact original message,
  `f"Gateway run-as user '{execution_user}' does not have access to agent
  '{target_agent}'"`. `target_agent` is passed explicitly rather than read
  off `agent_doc.name`, because the original code used `event.target_agent`
  for this message, not the Agent document's own name field — a detail a
  first pass at this refactor got wrong and a test caught (see Verification).
  A missing `execution_user` reproduces the existing
  `"Gateway is disabled or has no Run as user"`-adjacent rejection path
  (`"Gateway has no Run as user"`) defensively, though the real call site
  already short-circuits on that earlier.
- `TRIGGER_FLOW_WEBHOOK` (context: `{"owner": ...}`): resolves
  `run_as_user = owner or "Administrator"` and always reports `authorized =
  True` — there genuinely is no per-Agent gate at this layer, and inventing
  one would be a behavior change, not a refactor. The call site's
  `frappe.set_user(identity.run_as_user)` is byte-for-byte equivalent to the
  original `frappe.set_user(defn_doc.owner or "Administrator")`.
- `TRIGGER_DOC_EVENT` (context: `{"initiating_user": ..., "current_user":
  ...}`): if there's no initiating user, or it already matches the current
  session user, resolves to `current_user` with no lookup at all (avoids an
  unnecessary `frappe.db.exists` call on the hot, common path — a doc-event
  fired by the acting user themselves). Otherwise checks
  `frappe.db.exists("User", initiating_user)`: if it exists, resolves to it;
  if not, falls back to `current_user`, exactly as before.

## The one fix folded in, per the ticket's own instruction

**Doc-event silent-fallback-to-Administrator gap** (audit's "Exception
handling" section, `agent_hooks.py:145-149`): when `initiating_user` had
been deleted, the code caught `frappe.DoesNotExistError` from
`frappe.set_user()` and silently continued as whatever identity the
background worker already had — no log entry, so an operator investigating
"why did this doc-event agent run as Administrator instead of the person who
triggered it" had nothing to find. This was cleanly addressable inside the
new helper's natural surface area (it already has to decide the doc-event
fallback), so it's fixed here: the same fallback now also calls
`frappe.log_error(...)`, tagged `"Doc Event Agent identity fallback"`,
naming both the deleted user and the identity actually used
(`RunIdentityResult.fallback_reason`). The *fallback itself* — still
falling back to the current session user rather than aborting the run — is
unchanged; only the silence is fixed. Aborting the run instead would be an
actual behavior/policy change, out of scope for a "not a behavior change"
refactor ticket.

## What was investigated and explicitly **not** folded in

**The brittle substring-match no-adapter-installed carve-out**
(`gateway_service.py`, `if "No installed Gateway Adapter supports this
channel" in str(exc):`), also named in the ticket as a candidate fold-in.
Not touched: it lives in the *delivery* path (`send_gateway_reply`'s failure
handling), not the *identity/authorization* path this ticket's helper
covers — it has nothing to do with "who runs this agent," and forcing it
into `resolve_run_identity_and_authorize`'s surface area for the sake of
using this PR as a vehicle would be exactly the scope creep the ticket warns
against. It is a real, already-filed, separate finding
(`HUF_INTEGRATIONS_GATEWAYS_AUDIT.md:131`, Low severity) with its own
natural fix (match on an exception subtype/attribute instead of `str()`
substring matching) that belongs in a change touching `send_gateway_reply`
and its callers, not this one.

## Verification

Pure unit tests, run against the `intg-gw-audit` bench's Python environment
(inside the `frappe_docker_devcontainer-frappe-1` container) with
`PYTHONPATH` pointed at an isolated copy of this worktree's `huf` package —
the same technique GW-08 used, and for the same reason: the bench's own
`apps/huf` checkout was dirty with sibling clusters' in-progress work
(verified via `git status` before and after; unchanged, 17 modified/new
paths either side) and was never touched, read from, or written to.

Modules compared, baseline (this branch immediately after cherry-picking
GW-08's `2c2e62ee`, before any GW-11 change) vs. after:
`huf.ai.tests.test_gateway_service`, `huf.ai.tests.test_agent_access`,
`huf.ai.tests.test_run_agent_sync_guest_safeguards`,
`huf.ai.tests.test_phase1_security`,
`huf.ai.tests.test_media_agent_access_guard` (all four call sites'
behavior-test coverage, so far as dedicated test files exist for them —
`flow_api.py` and `agent_hooks.py` have no dedicated test modules in this
codebase to begin with; their behavior is exercised indirectly via
`test_phase1_security` and covered directly, for the shared helper, by the
new test module below):

- **Baseline**: `Ran 61 tests`, `FAILED (errors=21)`.
- **After** (same 5 modules): `Ran 61 tests`, `FAILED (errors=21)` — the
  identical 21 named errors, byte-for-byte (`diff` on the sorted
  `ERROR:`/`FAIL:` lines was empty). All 21 are pre-existing
  `RuntimeError: object is not bound` / `AttributeError: flags` failures
  from `IntegrationTestCase`-based classes and doctype-permission
  integration tests that require a bound Frappe site and only run under
  `bench run-tests` — the same category GW-08 documented. Zero regressions,
  zero new failures.
- **With the new test module added** (`+
  huf.ai.tests.test_run_identity_authorization`): `Ran 76 tests`, `FAILED
  (errors=21)` — same 21 errors; all 15 new tests pass.

One real bug was caught by this process, not just claimed fixed: an early
draft of the gateway branch used `agent_doc.name` for the rejection
message's agent identifier instead of `event.target_agent` (the original
code's actual field). `test_non_entitled_execution_user_is_rejected_at_the_pre_gate`
(the existing GW-08 test, asserting `"Support Agent" in
rejection["error_message"]` against a `MagicMock` whose `.name` is an
auto-generated mock attribute, not `"Support Agent"`) failed immediately
against that draft and was the reason `target_agent` is passed explicitly
in the `TRIGGER_GATEWAY` context rather than read off the Agent doc.

**New tests** (`test_run_identity_authorization.py`), one class per trigger
surface, all pure `unittest.mock`-based (no live site needed):

- `TestDirectApiSurface`: entitled+capable user authorized; non-entitled
  user rejected with the original message; entitled-but-no-`agent.use`-
  capability user rejected with the original, differently-worded message;
  Guest on an `allow_guest=1` agent authorized without ever touching
  `frappe.get_roles` or `has_capability` (mirrors the original
  Guest-skips-the-capability-check behavior).
- `TestGatewaySurface`: entitled `execution_user` authorized; non-entitled
  `execution_user` rejected with both the user and the (event-supplied)
  agent name in the message; missing `execution_user` rejected; and a
  regression guard, `test_allow_guest_alone_does_not_entitle_a_named_execution_user`,
  proving the post-GW-08 semantics survived this refactor — `allow_guest=1`
  alone still does not admit an arbitrary named `execution_user`.
- `TestFlowWebhookSurface`: resolves to the given owner; falls back to
  `"Administrator"` when the Flow Definition has no owner.
- `TestDocEventSurface`: no initiating user stays on the current session
  user without any `frappe.db` lookup; a same-as-current initiating user is
  also a no-op lookup; an existing initiating user is used; and the GW-11
  fold-in fix — a deleted initiating user falls back to the current user
  *and* calls `frappe.log_error` exactly once, naming the deleted user.
- `TestUnknownTriggerSurface`: an unrecognized `trigger_surface` value
  raises via `frappe.throw`, rather than silently doing nothing or picking
  an arbitrary surface's behavior.

**A test-isolation note, not a behavior issue**: the `direct_api` rejection
reasons and the "unknown trigger surface" message are deliberately
*plain, untranslated strings* inside `agent_access.py`, with `_()`
translation applied once, by the call site, at the moment it actually
`frappe.throw()`s (see `agent_integration.py`'s
`frappe.throw(_(identity.reason), frappe.PermissionError)`). An earlier
draft called `_()` inside the helper itself; that made the new pure unit
tests order-dependent — when run after certain other test modules in the
same process, real `frappe._()` reached into `frappe.cache`/logger internals
that are only valid under a bound site, and the test would fail with an
unrelated `AttributeError` depending on run order. Moving the `_()` call to
the throw site fixes the test fragility and is behavior-neutral: `_()`'s
translation lookup is keyed on the string's content, not on which line of
code invokes it, so the final user-facing (and possibly translated) message
text is unchanged.
