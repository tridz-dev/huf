# Plan 003: Make flow_webhook authentication mandatory and constant-time (fail closed)

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 540b535..HEAD -- huf/ai/flow_api.py`
> If `flow_api.py` changed since this plan was written, compare the "Current
> state" excerpt against the live code before proceeding; on a mismatch, treat
> it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: S
- **Risk**: MED
- **Depends on**: none (independent of 001/002; may run anytime, but reuses the `huf/ai/tests/` package created in 001 — if that dir is absent, create it)
- **Category**: security
- **Planned at**: commit `540b535`, 2026-06-13

## Why this matters

`flow_webhook` is a guest-callable endpoint (`@frappe.whitelist(allow_guest=True)`) that starts and runs a flow. Today its auth is fail-OPEN in two ways: if the flow's entry node is not a `trigger.webhook` (so `entry_node` is `None`), the auth block is skipped entirely and ANY active flow can be triggered by an unauthenticated guest; and if the webhook trigger's `auth` config is empty, no key is required. The key comparison `webhook_key != expected_auth` is also non-constant-time (a timing side channel for key recovery). The concrete cost: an anonymous internet user can execute arbitrary active flows on the instance, and brute-force the webhook key via timing. This plan makes auth mandatory and fail-CLOSED — reject unless the entry node is a configured webhook trigger with a non-empty key — and uses a constant-time comparison.

## Current state

File: `huf/ai/flow_api.py` — `flow_webhook` is the only guest-callable flow trigger.

Verified excerpt — `huf/ai/flow_api.py:331-365`:

```python
@frappe.whitelist(allow_guest=True)
def flow_webhook(flow_id: str, webhook_key: str | None = None) -> dict:
	...
	if not frappe.db.exists("Flow Definition", flow_id):
		frappe.throw(_("Flow '{0}' not found").format(flow_id), frappe.DoesNotExistError)

	defn_doc = frappe.get_doc("Flow Definition", flow_id)
	if defn_doc.status != "Active":
		frappe.throw(_("Flow '{0}' is not active").format(flow_id))

	defn = json.loads(defn_doc.definition_json) if isinstance(defn_doc.definition_json, str) else defn_doc.definition_json

	# Validate webhook auth
	nodes = defn.get("nodes", [])
	entry_node = None
	for n in nodes:
		if n.get("id") == defn.get("entry") and n.get("type") == "trigger.webhook":
			entry_node = n
			break

	if entry_node:
		expected_auth = entry_node.get("config", {}).get("auth")
		if expected_auth and webhook_key != expected_auth:
			frappe.throw(_("Invalid webhook key"), frappe.AuthenticationError)
```

Confirmed problems:
- (a) `entry_node` is `None` when the entry node's type is not `trigger.webhook` → the whole `if entry_node:` block is skipped → no auth.
- (b) `expected_auth` falsy (empty/missing) → `if expected_auth and ...` short-circuits → no auth.
- (c) `webhook_key != expected_auth` is a plain string compare → not constant-time → timing oracle.

The `auth` value lives in `entry_node["config"]["auth"]` inside the Flow Definition's `definition_json`. It is a per-flow webhook secret (NOT a Frappe Password field — it is plaintext inside the JSON definition). Treat it as a credential: never log or echo it.

Flow Definition doctype facts (verified from `flow_definition.json`): `flow_id` is a `reqd=1` Data field, and `definition_json` is a `reqd=1` JSON field. The webhook resolves the doc via `frappe.db.exists("Flow Definition", flow_id)` / `frappe.get_doc("Flow Definition", flow_id)` — i.e. `flow_id` here is used as the document `name`. A test fixture must set the doc `name` equal to the `flow_id` it will call with (or the doctype's autoname must derive name from flow_id — confirm before assuming).

Repo conventions: raises use `frappe.throw(_("msg"), frappe.AuthenticationError)`. Test classes use `FrappeTestCase` from `frappe.tests.utils` (see `huf/huf/doctype/agent_chat/test_agent_chat.py`).

## Commands you will need

| Purpose          | Command                                                                          | Expected on success |
|------------------|----------------------------------------------------------------------------------|---------------------|
| Run flow_api test| `bench --site <sitename> run-tests --app huf --module huf.ai.tests.test_flow_api`| `OK`                |
| All app tests    | `bench --site <sitename> run-tests --app huf`                                     | `OK`                |
| Confirm hmac     | `grep -n "hmac" huf/ai/flow_api.py`                                               | ≥1 match            |
| Search webhook flows | `grep -rn "trigger.webhook" huf/`                                             | inspect results     |

Replace `<sitename>` with the bench site.

## Scope

**In scope** (the only files you should modify):
- `huf/ai/flow_api.py` — rewrite the auth block in `flow_webhook`; extract a pure helper for testability.
- `huf/ai/tests/test_flow_api.py` (create; create `huf/ai/tests/__init__.py` if plan 001 has not run).
- `plans/README.md` — status row update.

**Out of scope** (do NOT touch):
- The `@frappe.whitelist(allow_guest=True)` decorator — external webhooks legitimately need guest access. KEEP it. The fix is mandatory auth, not removing guest access.
- The payload-parsing block (flow_api.py:367-382) and the enqueue logic — unrelated.
- Other flow_api endpoints (`run_flow`, `approve_flow_run`, etc.) — they are NOT `allow_guest=True`; out of scope.
- `flow_engine.py`, `http_handler.py`, `flow_eval.py`.

## Git workflow

- Branch: `advisor/003-flow-webhook-auth`
- Commit: helper extraction + auth rewrite + tests, ideally one commit. Message style: conventional commits (`fix:`). Suggested: `fix: require constant-time auth for flow_webhook (fail closed)`.
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 0 (gate): Check for existing auth-less webhook flows

Before changing behavior, confirm no active flow currently relies on auth-less webhook triggering (which this fix would break).

Run: `grep -rn "trigger.webhook" huf/` and inspect any committed Flow Definition fixtures/JSON. Also, if you have bench DB access, the operator can check for active Flow Definitions whose entry node is a `trigger.webhook` with empty `config.auth`, or whose entry node is not a webhook at all but which are triggered via this endpoint.

If you find any in-repo or operator-confirmed active flow that depends on auth-less webhook triggering, STOP and report (see STOP conditions) — making auth mandatory would break it; the operator must decide.

**Verify**: `grep -rn "trigger.webhook" huf/` → review output; proceed only if no auth-less dependency is evident.

### Step 1: Add `import hmac` and extract a pure auth helper

In `huf/ai/flow_api.py`, add `import hmac` to the imports (the file currently imports `json`, `frappe`, `_`, `now_datetime` — add `import hmac` near the top, after `import json`).

Add a module-level pure helper that takes the parsed definition and the supplied key and returns a bool. This is the unit-testable core. Target shape (tabs):

```python
def _webhook_key_is_valid(defn: dict, webhook_key: str | None) -> bool:
	"""Return True only if the flow's entry node is a webhook trigger with a
	non-empty configured auth key that matches webhook_key (constant-time).

	Fails closed: returns False if the entry node is missing, is not a
	trigger.webhook, or has no/empty auth configured.
	"""
	entry_id = defn.get("entry")
	entry_node = None
	for n in defn.get("nodes", []):
		if n.get("id") == entry_id and n.get("type") == "trigger.webhook":
			entry_node = n
			break

	if entry_node is None:
		return False

	expected_auth = entry_node.get("config", {}).get("auth")
	if not expected_auth:
		return False

	return hmac.compare_digest(str(webhook_key or ""), str(expected_auth))
```

**Verify**: `grep -n "_webhook_key_is_valid\|import hmac\|compare_digest" huf/ai/flow_api.py` → all three present.

### Step 2: Replace the auth block in `flow_webhook` to use the helper and fail closed

Replace the entire block at flow_api.py:354-365 (the `# Validate webhook auth` comment through the `if entry_node:` block) with:

```python
	# Validate webhook auth — mandatory, fail closed.
	if not _webhook_key_is_valid(defn, webhook_key):
		frappe.throw(_("Invalid webhook key"), frappe.AuthenticationError)
```

This removes the `entry_node = None` fall-through (now any non-webhook entry or empty key is rejected) and uses the constant-time compare inside the helper. Do NOT log `webhook_key` or `expected_auth` anywhere.

Keep everything after (payload parsing at line 367+) unchanged.

**Verify**: `grep -n "if entry_node:" huf/ai/flow_api.py` → no matches (old fall-through removed).
**Verify**: `grep -n "_webhook_key_is_valid" huf/ai/flow_api.py` → called inside `flow_webhook`.

### Step 3: Write `huf/ai/tests/test_flow_api.py`

If `huf/ai/tests/__init__.py` does not exist (plan 001 not run), create it empty first.

Unit-test the pure helper `_webhook_key_is_valid` (no DB needed — preferred, lightweight):

```python
import frappe
from frappe.tests.utils import FrappeTestCase

from huf.ai.flow_api import _webhook_key_is_valid


def _defn(entry_type="trigger.webhook", auth="secret-key-123"):
	node = {"id": "n1", "type": entry_type}
	if auth is not None:
		node["config"] = {"auth": auth}
	return {"entry": "n1", "nodes": [node]}


class TestWebhookKeyAuth(FrappeTestCase):
	def test_correct_key_accepted(self):
		self.assertTrue(_webhook_key_is_valid(_defn(auth="secret-key-123"), "secret-key-123"))

	def test_wrong_key_rejected(self):
		self.assertFalse(_webhook_key_is_valid(_defn(auth="secret-key-123"), "wrong"))

	def test_missing_key_rejected(self):
		self.assertFalse(_webhook_key_is_valid(_defn(auth="secret-key-123"), None))

	def test_empty_supplied_key_rejected(self):
		self.assertFalse(_webhook_key_is_valid(_defn(auth="secret-key-123"), ""))

	def test_empty_configured_auth_rejected(self):
		# Fail closed: no configured auth means no access.
		self.assertFalse(_webhook_key_is_valid(_defn(auth=""), "anything"))

	def test_missing_config_rejected(self):
		self.assertFalse(_webhook_key_is_valid(_defn(auth=None), "anything"))

	def test_non_webhook_entry_rejected(self):
		# Entry node is not a trigger.webhook -> fail closed even with a key.
		d = _defn(entry_type="trigger.schedule", auth="secret-key-123")
		self.assertFalse(_webhook_key_is_valid(d, "secret-key-123"))

	def test_no_matching_entry_rejected(self):
		d = {"entry": "missing", "nodes": [{"id": "n1", "type": "trigger.webhook", "config": {"auth": "k"}}]}
		self.assertFalse(_webhook_key_is_valid(d, "k"))
```

OPTIONAL happy-path integration test (only if creating a Flow Definition fixture is straightforward in this bench): create an Active Flow Definition whose `name`/`flow_id` match and whose `definition_json` has a webhook entry node with a known auth key, then call `flow_webhook(flow_id, webhook_key=...)` and assert a `flow_run_id` is returned for the correct key and `frappe.AuthenticationError` for a wrong key. If the fixture/enqueue is heavy or flaky, MARK this as an integration TODO (an `@unittest.skip("integration TODO: needs Flow Definition fixture + worker")`) rather than writing a brittle test. The unit tests above are the required coverage; the integration test is optional.

**Verify**: `bench --site <sitename> run-tests --app huf --module huf.ai.tests.test_flow_api` → `OK`, 8 unit tests pass.

### Step 4: Run the full suite

**Verify**: `bench --site <sitename> run-tests --app huf` → `OK`.

## Test plan

- New file `huf/ai/tests/test_flow_api.py`: 8 unit tests on `_webhook_key_is_valid` covering correct/wrong/missing/empty supplied key, empty/missing configured auth (fail closed), non-webhook entry (fail closed), and no-matching-entry. Optional skipped integration test for the full endpoint.
- Structural pattern: model after `huf/huf/doctype/agent_chat/test_agent_chat.py` and plan 001's `huf/ai/tests/test_flow_eval.py`.
- Verification: per-module `OK`, then full-suite `OK`.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `grep -n "import hmac" huf/ai/flow_api.py` → present
- [ ] `grep -n "compare_digest" huf/ai/flow_api.py` → present
- [ ] `grep -n "_webhook_key_is_valid" huf/ai/flow_api.py` → defined and called in `flow_webhook`
- [ ] `grep -n "if entry_node:" huf/ai/flow_api.py` → no matches (fail-open path removed)
- [ ] `grep -n "allow_guest=True" huf/ai/flow_api.py` → still present on `flow_webhook` (guest access kept)
- [ ] `bench --site <sitename> run-tests --app huf --module huf.ai.tests.test_flow_api` → `OK`, 8 unit tests pass
- [ ] `bench --site <sitename> run-tests --app huf` → `OK`
- [ ] `git status --porcelain` shows ONLY `huf/ai/flow_api.py`, `huf/ai/tests/test_flow_api.py` (+ `__init__.py` if created, + README)
- [ ] `plans/README.md` status row for 003 updated to DONE

## STOP conditions

Stop and report (do not improvise) if:

- Step 0 finds an in-repo or operator-confirmed active flow that triggers via webhook WITHOUT auth (entry node not a webhook trigger, or empty `config.auth`). Making auth mandatory will break it — the operator must decide; do not proceed.
- The drift check shows `flow_api.py` changed since `540b535` and the auth block no longer matches the "Current state" excerpt.
- You cannot confirm that `flow_id` maps to the Flow Definition document `name` (needed for the optional integration test) — skip the integration test and note it; do NOT guess the autoname scheme.
- A unit test fails after one reasonable fix attempt, suggesting the helper logic differs from intent.
- `flow_engine.run_flow` or `create_flow_run` signatures differ from what `flow_webhook` calls (only relevant if you attempt the integration test).

## Maintenance notes

- The webhook `auth` key is stored PLAINTEXT inside `definition_json`. A stronger follow-up (deferred): store the webhook secret in a Frappe Password field on the Flow Definition or a child doctype, and compare against the decrypted value. Out of scope here; the constant-time compare is the immediate hardening.
- If new trigger types are added that should accept guest webhooks, `_webhook_key_is_valid` must be extended deliberately — the default is to reject anything that is not a `trigger.webhook` with a configured key. Keep it fail-closed.
- Reviewer should scrutinize: (1) the helper truly fails closed for `entry_node is None` and empty `expected_auth`; (2) `hmac.compare_digest` operands are both `str` (it raises on mixed `str`/`bytes`); (3) the key is never logged or returned in any error/response.
- Consider rate-limiting `flow_webhook` in a follow-up — constant-time compare blunts timing attacks but does not stop online brute force; Frappe rate-limit decorators or a fail-counter would help.
