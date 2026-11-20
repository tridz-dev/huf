# MCP Server: Huf as a Tool Provider

Status: proposal, no code written yet.

## What

Expose Huf's own procedures (and later, selected DocType operations) as MCP tools, so external
MCP clients — Claude Code, Claude Desktop, another Huf instance — can call into Huf over
MCP. This is Huf acting as an MCP **provider/server**, the mirror image of Huf's existing
MCP **client** role (Huf already consumes external MCP tools via `mcp_client.py` /
`mcp_oauth.py`).

This is item (c) from the PR #661 write-up's "What remains" section: "Huf as an
MCP server (expose Huf procedures to external agents) — not yet started, likely cheapest
since procedure_runtime.py already exists." This document is that plan.

## Goal

Decide and sequence the concrete implementation: what gets exposed as tools, which auth
patterns ship in v1 vs later, and how scoping maps onto Frappe's permission system — such
that a human can execute directly from the phased plan below without re-deriving any of the design
questions below.

## Why this proposal, and why first

Frappe already serves synchronous HTTP request-response. MCP over streamable-HTTP is
exactly that shape: a client POSTs a JSON-RPC request, gets a response, no server-held
session or subprocess required. This is confirmed on the client side too — Huf's own MCP
client already defaults to `streamable_http_client` in `mcp_client.py` (line ~317), with SSE
only as a legacy fallback. Building the provider side to match (streamable-HTTP primary)
needs no new process model, no new worker, no new session substrate — Frappe's existing WSGI
request cycle is sufficient.

Contrast this against the companion "Huf as an ACP client" proposal (real ACP,
JSON-RPC 2.0 over stdio, per the PR #661 write-up item (b)): that requires a
long-lived subprocess per remote agent, a capabilities handshake, and a transport Frappe has
no native model for. This proposal has no equivalent gap. That is why it should be sequenced
ahead of both the ACP-client work and the remaining Huf-to-Huf federation backend
(PR #661) — it is the cheapest, highest-leverage piece of the three tracks
discussed.

## Source

No repo/branch yet — this is plan-only. Implementation should start from `origin/pre-develop`.

Research grounding this plan was gathered live against a running bench (file:line
citations throughout) — not re-derived from training data. Where a claim below cites
a file:line, it was confirmed by reading that file directly.

## Key files

Existing Huf source files referenced below (read directly, not yet modified):
- `huf/ai/graph/procedure_runtime.py` — procedure execution engine, the primary tool surface.
- `huf/ai/procedure_approval_api.py` — existing Pending Review → Approved gate.
- `huf/ai/tools/gateway_pairing_tools.py` — **dead, unsafe precedent, do not model on this**
  (see §4d and §10).
- `huf/ai/gateway_service.py` — `approve_gateway_pairing`, the correct pairing-flow template.
- `huf/ai/mcp_oauth.py`, `huf/ai/mcp_client.py` — Huf's existing MCP client side, mirror
  candidates for provider-side connection registry and transport choice.

## Before implementation starts

1. Read this document in full, including the phased plan below.
2. Read the PR #661 write-up and the companion "Huf as an ACP client" proposal to confirm
   scope doesn't overlap beyond the shared open decisions noted below.
3. Get the open decisions below confirmed before writing any code — several (v1 auth
   default, procedures-only vs +CRUD, shared vs separate doctype layer,
   `gateway_pairing_tools.py` deletion timing) change what Phase 1 actually contains.
4. Once confirmed, branch from `origin/pre-develop` and start Phase 1.

## Constraints / gotchas

- **Never model any new whitelisted method on `huf/ai/tools/gateway_pairing_tools.py`.** It
  has no `@frappe.whitelist()` anywhere and every write path uses `ignore_permissions=True`
  unconditionally. It is dead code (referenced only by its own test file) but is a live
  hazard as copy-paste material. See §4d and §10 for the full warning — this is
  named there as an instance of "the #661 bug class" (an unwhitelisted-or-permission-check-free
  method that trusts caller state), the same class of bug as the unresolved critical finding
  on PR #661 (PR #661).
- Any new whitelisted method this proposal adds (pairing approval, token minting, procedure
  invocation via MCP) must check permission first, never trust client-supplied state for
  anything security-relevant, and follow `gateway_service.approve_gateway_pairing`'s pattern
  (`has_permission` check first, rate-limited, constant-time comparison for any code/token
  compare) — restated in full in §10.
- External exposure of a write procedure must never be laxer than internal binding. Internal
  write-procedure binding already requires `approval_status == "Approved"`
  (`agent_procedure_binding.py`'s `_guard_read_only`) — external MCP listing of the same
  procedure must require at least that.
---

## Phased plan

This is the working plan a human executes
from directly. No code has been written yet; everything below is design plus file:line
citations against code read live.

## 1. Problem statement, and why this is the cheapest piece on the table

Huf currently only acts as an MCP **client** — it consumes external MCP tools
(`mcp_client.py`, `mcp_oauth.py`). Nothing lets an external MCP client (Claude Code, Claude
Desktop, another Huf instance) call **into** Huf. This proposal builds that direction.

The central claim to make explicit: **MCP over streamable-HTTP is a synchronous
request-response protocol, and that is exactly the shape Frappe's WSGI request cycle already
serves.** No new process model, no new long-lived session, no new worker type is required —
a whitelisted Frappe endpoint that speaks the MCP wire format on top of ordinary HTTP
request/response is enough.

This is confirmed, not assumed: Huf's own MCP **client** side already defaults to
`streamable_http_client` (`mcp_client.py`, ~line 317), branching only to
`mcp.client.sse.sse_client` when `MCP Server.transport_type == "sse"`, which is treated as a
legacy fallback. If Huf's own client already prefers streamable-HTTP over SSE, the provider
side should match that preference for consistency and because it is the cheaper transport to
serve from Frappe's request cycle (no held-open connection, no separate event-stream worker).

Contrast this against the companion "Huf as an ACP client" proposal (real ACP —
JSON-RPC 2.0 over stdio, per the PR #661 write-up item (b)): that requires a
long-lived subprocess per connected agent and a capabilities handshake over a transport
Frappe has no native serving model for at all. It is a materially bigger build. This is the
concrete reason this proposal should be sequenced first: it reuses infrastructure Frappe
already has; the ACP-client proposal needs infrastructure Frappe does not have.

## 2. What gets exposed as MCP tools

**Primary surface (v1): procedures from `huf/ai/graph/procedure_runtime.py`.**

`Agent Procedure` already carries, in its `contract_section`: `input_schema` (JSON),
`output_schema` (JSON), `applicability` (JSON), `permission_envelope` (JSON), `is_read_only`,
`contains_writes`, `contains_code`, `approval_status` — denormalized from
`definition_json.contract`. This maps close to directly onto an MCP `tools/list` entry's
`inputSchema`/`outputSchema`. Concretely: schema authoring for MCP tool definitions is
**largely already solved** by the procedure contract system. This proposal needs a **mapper**
(Agent Procedure contract → MCP tool descriptor), not a new schema-authoring surface.

`execute_procedure(version, input_payload, *, tool_invoker, run_id=None, ...)`
(`procedure_runtime.py:942`) is the execution entry point: `input_payload` becomes the
`GraphContext` data namespace directly, and it returns a `ProcedureOutcome`
(`status: success|failed|not_applicable`, `output`, `error`, `tool_call_count`,
`tool_invocations`, `node_outputs`, `fallback`). `PROCEDURE_NODE_TYPES` is restricted to
`("tool.call", "transform", "condition", "foreach", "parallel", "validate", "output")` —
`agent.run` / `router.llm` / `human.approval` / `trigger.*` are excluded by construction
("no LLM anywhere in this path", enforced at versioning time by
`procedure_versioning.py`'s `assert_no_flow_only_nodes()`). This matters for MCP exposure:
every procedure callable via MCP is, by construction, a deterministic pinned graph, not an
open-ended agent loop — a much smaller thing to reason about as an external-facing tool.

`run_agent_procedure_run(run_name, *, agent_doc=None)` (`procedure_runtime.py:1158`) is the
frappe-facing entry that loads an `Agent Procedure Run` doc, takes a run lock
(`procedure_lock`), builds the `tool_invoker`, and persists one `Agent Procedure Step` row
per node. It reads `contract.get("permission_envelope")` at ~line 1239 — the envelope is
consumed at execution time, not just declared. The MCP-tool wrapper should call through this
same entry point, not `execute_procedure` directly, so the same run-tracking, locking, and
permission-envelope enforcement applies to MCP-triggered invocations as to internal ones.

**Secondary/advanced tier (v2+, opt-in, not default): raw DocType CRUD as tools.**

CRUD is more flexible but reintroduces the cost procedures exist to remove: the caller has to
re-derive the schema and permission shape on every call, rather than Huf having already
precomputed it. The framing of Huf's actual advantage over "just exposing an API"
is precomputed schema/permission/procedure knowledge — CRUD-as-tools throws that away.
Recommendation: procedures-first as the v1 default tool surface; CRUD-as-tools stays an
explicit, separately-flagged advanced tier, never the default (see open decision §9b).

## 3. What's already safe to expose, structurally

Two existing mechanisms do most of the safety work already:

- `is_read_only` on `Agent Procedure`.
- The Pending Review → Approved gate in `huf/ai/procedure_approval_api.py`:
  `request_procedure_approval(procedure_name)` lets any read-access user set
  `approval_status = "Pending Review"`; `approve_procedure(procedure_name, approve, note)` is
  role-gated to `APPROVAL_MANAGER_ROLES = ("System Manager", "Huf Manager")` (~line 38), sets
  `Approved`/`Rejected`, and stamps `approved_by`/`approved_at`.

The existing consumer of this gate is `agent_procedure_binding.py`'s `_guard_read_only`,
which refuses to bind or enable a **write** procedure (`is_read_only = 0`) for internal use
unless `approval_status == "Approved"`.

**Recommendation for external MCP exposure:**
- Read-only, Approved procedures are safe MCP tool candidates by default.
- Write procedures require the *same* Approved gate before being listed to an *external*
  caller — and this must never be laxer than the internal-binding bar. If anything, external
  exposure is a higher bar than internal binding, since the caller is outside Huf's own trust
  boundary entirely. Concretely: the MCP tool-list mapper should filter on
  `approval_status == "Approved"` for any procedure where `is_read_only == 0`, using the exact
  same check `_guard_read_only` already performs internally, not a new parallel check that
  could drift from it.

## 4. Auth — phased recommendation

Four options, each grounded in code read live.

### 4a. API key/secret — v1 default

**Confirmed live against a running bench, not just asserted**: Frappe core natively supports
`Authorization: token <api_key>:<api_secret>` for any whitelisted method.
`frappe/auth.py:625` calls `validate_auth_via_api_keys(authorization_header)`;
`:682` defines `validate_auth_via_api_keys`; `:694-698` decodes `"api_key:api_secret"`
(base64 or plain) and calls `validate_api_key_secret`; `:708-724` defines
`validate_api_key_secret`, which looks up the key and `get_decrypted_password`s the secret.
This was confirmed present in a running bench, not inferred from framework docs.

This makes API-key auth for an MCP provider **nearly free**: no new Huf validation code is
needed at all for the credential-check step. Keys are minted via Frappe's own User "API
Access" mechanism. The only new piece needed is a connection-registry doctype tracking which
external caller holds which key and what scope it maps to (see §5).

Recommend: part of the v1 default, alongside the pairing-code flow (§4d).

### 4b. OAuth 2.1 + PKCE as MCP provider — v3, not v1

**Confirmed live against a running bench**: Frappe core ships a real OAuth2 provider —
`frappe/integrations/oauth2.py` plus doctypes `OAuth Client`, `OAuth Bearer Token`,
`OAuth Authorization Code`, `OAuth Scope`, `OAuth Provider Settings`, `OAuth Client Role` —
all present under `apps/frappe/frappe/integrations/doctype/` in a live bench checkout. This
is not hypothetical or aspirational; it exists today.

Recommendation: Huf should **delegate** to this rather than build an OAuth provider from
scratch. The work on top is: (1) scope definitions that match Huf's procedure/permission
model (an OAuth scope per procedure-category or per approval-tier, not a generic
"read"/"write"), and (2) discovery metadata per RFC 8414/9728 so external MCP clients can
autodiscover the provider the same way Huf's own MCP client side already expects when
*connecting to other* OAuth-providing MCP servers — see `mcp_oauth.py`'s
`oauth_metadata_json` field and `oauth_discovery_status`, which exist specifically to consume
that metadata on the client side; the provider side needs to produce the mirror of it.

This is the largest of the four auth options. Recommend it as a v3 phase (§8), not v1 — it is
also the option least likely to be needed for the primary near-term use case (a developer
pointing Claude Code/Desktop at their own Huf instance), which is better served by §4d.

### 4c. Basic auth — simplest fallback, brief

Simplest possible option for the simplest server-to-server or local-dev cases. Should
probably not be the *default* given Frappe already has better-fitting native mechanisms
(API key, or the pairing flow) — but worth supporting as a fallback since it costs almost
nothing once API-key auth exists (same code path, different header parse). Not separately
phased; bundle into whichever phase touches auth-header parsing if there is demand for it.

### 4d. The pairing-code DX flow — v1 default for human-driven setups

This was explicitly requested: a pairing-code / magic-link flow like a CLI device-pairing UX.
Design it by extending `gateway_service.py`'s `approve_gateway_pairing` — this is **the
correct template** to build from, confirmed via full read:

- **Generation**: `_create_pairing_request()` (`gateway_service.py:270`):
  `code_suffix = secrets.token_hex(2).upper()` →
  `pairing_code = f"PAIR-{code_suffix}"` (4 hex chars). Idempotent — reuses an existing code
  if a Pending `Gateway Access Entry` already exists for `(gateway, provider, external_id)`.
- **TTL**: `expires_at = add_to_date(now_datetime(), minutes=int(gateway.pairing_ttl_minutes or 60))`
  — configurable per-Gateway, default 60 minutes.
- **Storage**: `Gateway Access Entry` doctype, `state = "Pending"`, inserted with
  `ignore_permissions=True` (acceptable here — it's a system-initiated pending-request record,
  not a grant of access).
- **Approval (canonical path)**: `approve_gateway_pairing(code_or_entry_name, notes)`
  (~line 389), decorated `@frappe.whitelist(methods=["POST"])` and
  `@rate_limit(limit=20, seconds=60)`. Correctly permission-checked:
  `frappe.has_permission("Gateway Access Entry", "write")` (~line 403) runs **before**
  anything else. Code lookup uses `secrets.compare_digest()` — constant-time comparison, with
  an explicit comment (~line 397-399) explaining why: a pairing code is guessable and this
  endpoint is otherwise unauthenticated-by-code, so timing must not leak match progress.
  Falls back to doc-name match for legacy callers.
- **What's minted**: this flow itself does not mint a separate bearer token — approval flips
  `Gateway Access Entry.state` to `Approved`, and later messages from that `external_id` are
  admitted by checking for an Approved entry (`expires_at` unset or future). It is an
  allowlist entry, not a bearer credential.

**Concrete flow for this proposal**: an MCP client (e.g. Claude Desktop) initiates a connection
attempt against a Huf instance. Huf shows a short pairing code (mirroring the `PAIR-XXXX`
format and `secrets.token_hex(2).upper()` generation) or a magic link in the Huf UI. The
logged-in user approves in-app — write-permission-checked, rate-limited, constant-time
compare, matching `approve_gateway_pairing`'s actual guarantees exactly. Only *then* is a
scoped bearer token/API-key pair minted and handed back to the waiting client (long-poll or a
second round trip).

**This is the one place the template needs extending, not just copying**: because MCP needs a
credential the client presents on *every* call, not just an allowlisted identity check,
approval must additionally mint a scoped API key/secret (§4a) at the moment of approval, not
merely flip a state flag. Use the same bounded pending-window pattern
(`pairing_ttl_minutes`, defaulted to 60) for the pending-approval window; the minted
credential's own lifetime is a separate, likely longer-lived, setting.

Recommend: this is the default DX for human-driven setups (Claude Desktop/Claude Code
connecting to a user's own Huf instance) in v1, alongside API-key auth for
programmatic/server-to-server cases.

### DEAD, UNSAFE precedent — do not model on this, under any circumstance

`huf/ai/tools/gateway_pairing_tools.py` (347 lines, full read) is an **older, duplicate**
implementation of the same pairing flow (`setup_gateway`, `list_pairing_requests`,
`approve_pairing_code`, `test_gateway_health`) with **no `@frappe.whitelist()` decorator
anywhere** and **no `frappe.has_permission()` check anywhere** — every write path uses
`ignore_permissions=True` unconditionally. Confirmed via `git grep`: referenced only by its
own test file; nothing in the codebase actually invokes it as a live tool or endpoint.

`gateway_service.py`'s own docstring for `approve_gateway_pairing` (~line 391-395) states it
"consolidat[es] the previously unreachable `gateway_pairing_tools.approve_pairing_code`...
into one whitelisted function reachable both ways" — i.e. this exact file was already
identified and superseded once, specifically because of this permission/reachability gap.
`test_gateway_service.py:463` independently calls it "the orphaned
`gateway_pairing_tools.approve_pairing_code`."

Three explicit actions from this:
1. **Any new MCP-provider pairing code in this proposal must be modeled on
   `gateway_service.approve_gateway_pairing`, never on `gateway_pairing_tools.py`.**
2. **Recommend `gateway_pairing_tools.py` be flagged for deletion** as part of this proposal's
   Phase 1 or a fast-follow — it is dead code that could mislead a future implementer (human
   or agent) into copying an unsafe pattern. Low-risk, small, see open decision §9d.
3. **Name this failure mode explicitly**: an unwhitelisted-or-permission-check-free method
   that trusts caller state is **"the #661 bug class"** (see §10) — a recurring pattern to
   actively guard against in this proposal, not a one-off curiosity.

## 5. Scoping and permissions

How does an external caller's access map onto Frappe's permission system?

- **(a) Per-connection role binding** (recommended, primary mechanism): the paired/keyed
  connection acts as a specific Frappe user, or is bound to a role, so Frappe's *native*
  permission system does the enforcement — not a bespoke allowlist reimplementing what Frappe
  already does.
- **(b) Per-procedure allowlist** (recommended, additional layer): tighter scoping than a role
  alone provides — a connection might have a role that could technically see many procedures,
  but should only be allowed to invoke a specific subset via MCP.

**Evaluate reusing `Remote Agent Policy`** from the #661 RFC (`allowed_agents`/`allowed_roles`
JSON, `max_timeout_seconds`, `max_tokens`, `requires_human_approval`, `audit_level`) —
currently unbuilt (the PR #661 write-up confirms it as a stub doctype). Its
*purpose* (governance/scoping for an external connection) fits an MCP-caller policy well
regardless of which RFC it originated in. Recommend: yes, reuse the shape. **Open decision**:
this doctype should probably be shared/promoted to a common location rather than owned
exclusively by either this proposal or PR #661 — flagged, not resolved, in §9c.

## 6. Huf-to-huf over this same MCP server

State this explicitly: another Huf instance calling in via this proposal's MCP server is **just
another MCP client** using API-key or OAuth auth (§4a/§4b) — no separate mechanism needed.
This is visibly simpler than PR #661's bespoke `HufNativeAdapter` / manifest-fetch / polling
approach (PR #661).

Recommendation (not a mandate — flagged as an open decision, §9c): once this proposal's
connection-registry and auth layer exist, evaluate retiring #661's custom protocol in favor
of huf-to-huf-over-MCP, or at minimum share the connection-registry/auth layer between the two
tracks rather than duplicating it. The user may still want #661's SSRF-hardened adapter
methods for cases MCP doesn't fit well, or may want full consolidation — this plan does not
resolve that, it only surfaces the option.

## 7. Transport

MCP over streamable-HTTP as primary, matching the client side (`mcp_client.py`, ~line 317:
default branch uses `mcp.client.streamable_http.streamable_http_client`; only
`transport_type == "sse"` uses `mcp.client.sse.sse_client`). SSE is a legacy fallback only,
on both sides. Neither file pins an explicit `protocolVersion` string — negotiation is
delegated to the official `mcp` SDK's `ClientSession.initialize()`; the provider side should
use the equivalent server-side primitive from the same SDK rather than hand-rolling protocol
negotiation. Restated from §1: this, plus the "Frappe is already a request-response server,"
is the concrete reason this proposal is cheaper and faster to ship than the ACP-client proposal.

## 8. Phased plan

Sizing is relative (small / medium / large), not time-estimated.

### Phase 1 (v1) — small/medium
- Pairing-code flow (§4d), modeled on `gateway_service.approve_gateway_pairing`.
- API-key auth (§4a) — thin wrapper over Frappe's native `validate_auth_via_api_keys`.
- Procedures-only tool surface: read-only, Approved procedures first (§2, §3).
- Per-connection role-based scoping (§5a).
- New: connection-registry doctype (mirrors `MCP Server`'s shape on the client side, but for
  registering *inbound* connections) + a tool-schema mapper (Agent Procedure contract → MCP
  tool descriptor).
- Needs almost no new Frappe-core capability — this is why it's Phase 1.
- Depends on: nothing outside this proposal. Does not depend on PR #661 landing
  anything.

### Phase 2 — medium
- Write-procedure exposure, gated by the existing approval flow (§3) — external listing
  requires `approval_status == "Approved"`, same bar as internal binding, never laxer.
- Per-procedure allowlist (§5b), likely via the `Remote Agent Policy` shape (§5, §9c).
- Depends on: Phase 1's connection registry and tool mapper.

### Phase 3 — large
- OAuth 2.1 provider delegation (§4b) for third-party/compliance MCP clients.
- Discovery metadata (RFC 8414/9728) matching what `mcp_oauth.py` already expects when Huf is
  the *client* connecting to other providers.
- Depends on: Phase 1's scope model existing to map onto OAuth scopes.

### Phase 4 (optional, evaluate) — large
- CRUD-as-tools advanced tier (§2, opt-in only, never default).
- Huf-to-huf-over-MCP consolidation with PR #661 (§6) — evaluate retiring or
  partially retiring #661's custom protocol.
- Depends on: Phase 1-3 being stable, and an explicit decision from the user on §9c.

## 9. Open decisions — ask, do not silently resolve

- **(a) Confirm v1 auth default.** Recommendation: pairing-code (§4d) for human-driven setup +
  API-key (§4a) for programmatic/server-to-server; OAuth (§4b) deferred to Phase 3. This is a
  recommendation, not a decision — confirm with the user before Phase 1 starts.
- **(b) Procedures-only vs procedures+CRUD in v1.** Recommendation: procedures-only (§2).
  Confirm with the user — CRUD-as-tools is real demand in some setups even if it reintroduces
  the schema-rederivation cost this proposal exists to avoid.
- **(c) Is the connection-registry / policy doctype layer shared with
  the companion "Huf as an ACP client" proposal and PR #661, or kept separate?** Flagged
  explicitly, not resolved. The companion "Huf as an ACP client" proposal exists — read
  its own write-up before deciding. `Remote Agent Policy` (§5) is the concrete point of
  potential overlap.
- **(d) Should `huf/ai/tools/gateway_pairing_tools.py` be deleted now, as part of this
  proposal's Phase 1, or left for a separate cleanup task?** This is a small, low-risk action —
  recommend doing it as part of Phase 1 (it's dead code, confirmed unreferenced except by its
  own test), but surface it explicitly rather than silently deleting it without confirmation,
  since it touches a file outside this proposal's own directory.
- **(e) Does MCP-server sequencing come ahead of the companion "Huf as an ACP client" proposal?** The section above recommends MCP as cheapest/highest-leverage and sequenced first. This assumes ACP-client work stays in scope but is deprioritized. Confirm with the user before Phase 1 starts — the companion "Huf as an ACP client" proposal may be the higher priority if external coding-agent interop is the primary goal.

## 10. Risks

PR #661 has an **unresolved critical** security finding: a read-only
Huf User can exfiltrate a stored `auth_secret` via whitelisted doc methods that trust
client-supplied doc state and bypass `validate()`. This is directly relevant here, not just
adjacent — this proposal adds several new whitelisted methods (pairing approval, token minting,
procedure invocation via MCP), and the same failure mode is available to repeat.

**Mandatory for every new whitelisted method this proposal adds**:
1. Check write/appropriate permission explicitly as the first line of the method — never rely
   on DocType-level default permissions to do this implicitly.
2. Never trust client-supplied state for anything security-relevant. Re-read from DB inside
   the method; do not accept a doc's current in-memory field values as ground truth for a
   permission or identity decision.
3. Follow `gateway_service.approve_gateway_pairing`'s actual pattern as the house-correct
   template: `has_permission` check first, rate-limited (`@rate_limit`), constant-time
   comparison (`secrets.compare_digest`) for any code/token comparison.

Restated from §4d because it matters twice: `huf/ai/tools/gateway_pairing_tools.py` is a
second, concrete instance of this exact bug class already sitting in the codebase — no
`@frappe.whitelist()`, no `frappe.has_permission()`, `ignore_permissions=True` on every write.
It is dead (unreferenced outside its own test) but must never be used as a template. Name
this pattern **"the #661 bug class"** — an unwhitelisted-or-permission-check-free method that
trusts caller state — and treat any new code in this proposal that resembles it as a blocking
review finding, not a style note.
