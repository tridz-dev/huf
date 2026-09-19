# GW-08 decision record: what identity authorizes a Gateway-triggered Agent run

- Status: Accepted, implemented
- Date: 2026-09-05
- Track item: GW-08
- Scope: `huf/ai/gateway_service.py` (`process_gateway_event`), tests. Explicitly out of scope: GW-11 (unified identity model), GW-12 (Gateway/Integration doctype permissions).

## Decision

**Option (b), implemented as a substitution rather than a deletion.**

`process_gateway_event` no longer authorizes the run as `Guest`. It authorizes it as the
Gateway's configured `execution_user` — the same principal the run actually executes as
two lines later at `frappe.set_user(gateway.execution_user)`.

```python
# before
assert_agent_access(agent_doc, user="Guest")   # -> bool(agent_doc.allow_guest), nothing else

# after
if not check_agent_access(agent_doc, gateway.execution_user):
    reject(f"Gateway run-as user '{...}' does not have access to agent '{...}'")
```

I did not simply delete the pre-gate. Deleting it would have left the only remaining check
buried inside `run_agent_sync`, surfacing as a generic exception rather than a `Gateway
Event` with a `status` and a readable `error_message` — a regression in operability and
adjacent to GW-09's "failures must be legible" theme. Keeping the gate and correcting its
principal preserves the rejection surface and makes the pre-gate agree with, rather than
contradict, the deeper check.

## Why this and not option (a)

The audit framed this as "is Guest-authorization the intended permanent semantics?".
Investigating the code, I do not think it ever was — it is an outlier that contradicts an
authorization model the same codebase already implements deliberately elsewhere.

**1. The execution_user model already exists and is already enforced at save time.**
`Gateway.validate` (`huf/huf/doctype/gateway/gateway.py`, tagged ST-04.4) already does two
things: it constrains `execution_user` to an allowed role (default `Huf Gateway User`,
overridable via the `huf_gateway_execution_roles` hook), and — the decisive detail —
`_validate_agent_access()` calls **`check_agent_access(agent, self.execution_user)`** to
refuse an enabled Gateway whose `execution_user` cannot reach its `default_agent`. So the
product already asserts, at gateway-save time, that the authorizing principal for a gateway
run is `execution_user`. The Guest pre-gate at run time was a second, later, contradictory
model layered on top of that one. My change makes the run-time gate use the same predicate
against the same principal as the existing save-time gate. This is convergence on an
existing decision, not a new one.

**2. The Guest pre-gate was not protecting against the thing its rationale describes.**
The patch rationale (`huf/patches/v1/preserve_gateway_agent_access.py`) is: "there is no
mechanism mapping an external gateway sender to a specific HUF user, so gateway-routed runs
are authorized as if the caller were Guest." The premise is true; the conclusion does not
follow. The anonymous *sender* is not the source of authorization in this design and never
was — the *admin who configured the Gateway and chose `execution_user`* is. Authorizing as
Guest does not add a check about the sender; it replaces a real, scoped check
(`allowed_users` / `allowed_roles` / `allow_all_users` / owner / capability) with a single
boolean that is about something else entirely.

**3. The residual thing the Guest gate did provide is a consent signal, and it is the
wrong instrument for it.** Honestly stated, `allow_guest=1` did encode one thing worth
having: the Agent owner's conscious acceptance that arbitrary strangers may drive this
Agent. That is a real and distinct question from "is this principal entitled". But
`allow_guest` is a terrible instrument for it, because it is *also* the sole gate on two
endpoints decorated `@frappe.whitelist(allow_guest=True)`: `run_agent_sync`
(`agent_integration.py:1147`) and `run_agent_sync_chat` (`chat_api.py:26`). Under option
(a), the price of connecting an Agent to Telegram is publishing that same Agent to
unauthenticated callers on the open REST API. That is a strictly larger exposure than the
integration requires, forced as a precondition of the integration. A consent gate that can
only be satisfied by taking an unrelated and larger risk is not a safety feature.

**4. Option (a) documents a bad coupling instead of removing it.** Option (a)'s deliverable
is a better error message. That message would read, accurately: "to use this Agent behind a
Gateway you must also expose it to anonymous internet callers." Writing that sentence down
clearly is an improvement over the current misleading message, but the correct response to
being able to write that sentence is to make it untrue.

**5. The new model is strictly stricter for the gateway path, not looser.** Under the old
gate, `allow_guest=1` admitted *any* Gateway to *any* such Agent regardless of who
`execution_user` was. Under the new gate, `execution_user` must genuinely be entitled:
owner, System Manager, `agent.view_all`/`agent.edit` capability holder, listed in
`allowed_users`, holding a role in `allowed_roles`, or `allow_all_users=1` on an Agent with
empty lists. Then, after `frappe.set_user(execution_user)`, `run_agent_sync` re-checks the
same predicate *and* additionally requires the `agent.use` capability
(`agent_integration.py:~1213-1219`) — a requirement the Guest branch skipped entirely,
since it is guarded by `if frappe.session.user != "Guest"`. So the previous design was, for
a scoped Agent, weaker than what replaces it.

## Is the surviving `run_agent_sync` check sufficient? (verified, not assumed)

Yes, for the specific question asked: it validates real, scoped entitlement of the acting
principal against the target Agent, not merely that the Agent exists. Verified by reading
`agent_integration.py`:

- Existence and Guest-visibility are handled first, with a deliberate oracle-avoidance
  invariant (missing Agent and `allow_guest=0` Agent throw an identical `PermissionError`).
- `agent_doc.disabled` is rejected.
- `assert_agent_access(agent_doc, user=frappe.session.user)` — the full
  `check_agent_access` ladder above. In the gateway path `frappe.session.user` is
  `execution_user`, because `process_gateway_event` calls `frappe.set_user()` before
  invoking it.
- `has_capability(frappe.session.user, "agent.use")` is additionally required for any
  non-Guest principal.
- All of the above run before the `now` / queue branch, so both execution modes are covered.

Two caveats I am explicit about rather than glossing:

- This check is **capability- and allowlist-based, not per-Gateway-binding-based**. An
  entitled `execution_user` can reach any Agent it is entitled to, including one bound to a
  different Gateway. Routing, not authorization, is what confines it to one Agent, and
  routing is not a security boundary. This is a property of the pre-existing execution-user
  model, unchanged by this decision, and is GW-11 territory.
- `check_agent_access`'s `for_execution` parameter is currently unused (view and run share
  one rule set). If execution ever needs stricter rules, that is where it goes.

## Exposure of `run_agent_sync` / `run_agent_sync_chat`: unchanged by this decision

Stated explicitly, because the backlog asks for it.

Those two endpoints are separate whitelisted entrypoints carrying their own
`@frappe.whitelist(allow_guest=True)` decorators. Their exposure to an unauthenticated
caller is a function of each Agent's own `allow_guest` flag and nothing else.
`gateway_service.py`'s pre-gate is not in their call path and never was. Changing or
removing it therefore does **not** make them more exposed, and does not by itself close
that hole either.

What this change does do is remove the *pressure* that was widening the hole. Previously,
every new Agent-target Gateway required flipping `allow_guest=1`, and the
`preserve_gateway_agent_access` migration flipped it on every already-bound Agent at once.
Now a Gateway integration no longer requires it, and — the operationally useful part —
deployments that only set `allow_guest=1` to satisfy the gateway gate **can now turn it
back off** without breaking their gateway. That is a remediation path that did not exist
before. Actually enumerating and closing those flags on existing sites is deployment work,
not code, and is called out under residual risk below.

## Alternatives considered and rejected

- **(a) Keep Guest coupling, improve the error message and add a save-time check.**
  Rejected: it makes a bad coupling legible instead of removing it, and leaves every
  gateway-using deployment obliged to run its Agents on a public unauthenticated endpoint.
  Sound as a stopgap if the coupling were load-bearing; investigation showed it is not.
- **(c) Remove the pre-gate outright, rely solely on `run_agent_sync`.** Rejected on
  operability, not safety: it is safe (the deeper check is equivalent), but a rejected
  gateway message would surface as a raw exception rather than a `Gateway Event` with a
  status and reason, degrading exactly the diagnosability GW-09 is trying to improve.
- **(d) Introduce a dedicated "allow gateway invocation" consent flag on Agent**, separating
  owner-consent-to-anonymous-exposure from principal-entitlement properly. This is the
  theoretically cleanest answer and I would support it. Rejected here as out of scope: it
  requires a new Agent doctype field plus a migration, neither of which is in this item's
  allowed change surface, and it overlaps GW-11's remit. Recorded as a follow-up.
- **Authorize as the Gateway *owner* rather than `execution_user`.** Rejected: it would
  re-introduce a second identity model in the very place we are collapsing one, and
  `execution_user` is the documented least-privilege service principal for exactly this.

## Residual risk

1. **Owner consent is no longer signalled.** A user who can configure a Gateway and who is
   themselves entitled to Agent X can now expose X to an anonymous channel without X's
   owner opting in. Bounded by `Gateway.validate`'s role constraint on `execution_user` and
   by that user needing genuine entitlement to X, and note the old design did not prevent
   this either — it merely required the same actor to take a more damaging action
   (`allow_guest=1`) first. Proper fix is alternative (d) or GW-11.
2. **Who may create a Gateway at all is unresolved** — that is GW-12, untouched here. This
   decision's safety rests partly on Gateway configuration being an administrative act.
3. **The `allow_guest=1` flags the migration already set remain set.** Nothing here unsets
   them. Deployments should audit gateway-bound Agents and clear `allow_guest` where it was
   only ever set to satisfy the old gate. Worth a release note; it is the actual
   product-owner-facing risk the audit identified.
4. **`preserve_gateway_agent_access.py`'s docstring is now historically accurate but
   describes semantics that no longer apply.** The patch is idempotent and already run, so
   this is documentation drift, not a behavioural issue; the patch file was outside this
   item's allowed change surface. Flagged for a follow-up docs pass.
5. **Gateway Binding-routed agents are still only checked at run time**, not at
   Gateway-save time — `Gateway.validate._validate_agent_access` covers `default_agent`
   only, and Gateway Binding is a separate doctype whose controller was outside scope.
   Extending the save-time check to bindings would move the failure earlier and is a
   worthwhile small follow-up.

## Verification

Pure unit tests, run against the `intg-gw-audit` bench's Python environment with
`PYTHONPATH` pointed at an isolated copy of this worktree's `huf` package. The bench's own
`apps/huf` checkout was **not** touched — it was dirty with sibling clusters' work at the
time (verified via `git status` before starting), so no file there was modified, staged, or
reset.

Baseline (HEAD, unmodified) vs. this change, `huf.ai.tests.test_gateway_service` +
`huf.ai.tests.test_agent_access`:

- baseline: `Ran 50 tests`, `FAILED (errors=12)`
- this change: `Ran 55 tests`, `FAILED (errors=12)` — the same 12 named errors

All 12 are pre-existing `RuntimeError: object is not bound` failures from
`IntegrationTestCase` classes that require a bound Frappe site context and are only
runnable under `bench run-tests`. Zero new failures; the 5 added tests all pass.
`test_run_agent_sync_guest_safeguards`, `test_phase1_security`,
`test_media_agent_access_guard` and `test_router_set_user` were also compared
baseline-vs-change and are byte-identical (10 pre-existing setUpClass errors either side).

New tests:

- `TestGatewayAgentAdmissionIdentity.test_non_entitled_execution_user_is_rejected_at_the_pre_gate`
  — the acceptance criterion for option (b). A non-entitled `execution_user` is rejected,
  the check is asserted to have been asked about `execution_user` (not `"Guest"`), the
  rejection message names both principal and Agent, and `frappe.set_user` is asserted
  never to have been called, i.e. no impersonation occurred.
- `TestGatewayAgentAdmissionIdentity.test_allow_guest_zero_agent_is_reachable_when_execution_user_is_entitled`
  — the coupling is gone: an `allow_guest=0` Agent runs behind a Gateway.
- `TestSurvivingRunAgentSyncCheck.{test_non_entitled_execution_user_rejected_by_assert_agent_access,
  test_entitled_execution_user_accepted_by_assert_agent_access}` — the surviving deeper
  check discriminates correctly on scoped entitlement.
- `TestSurvivingRunAgentSyncCheck.test_allow_guest_alone_does_not_entitle_a_named_execution_user`
  — regression guard proving the semantics genuinely changed: `allow_guest=1` no longer
  admits an arbitrary named principal, though it still admits `Guest`.
