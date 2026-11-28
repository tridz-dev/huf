# Template registry and status sync: gap audit (H-W2-16)

Audit only; no code changed. Compared Huf `hf/integration` @ d249e11a2 with Happiol `hf/integration` @ bfec873d (read-only).

Huf files: `huf/ai/gateway_adapters/whatsapp_bridge.py` (sync, state, send), `whatsapp_templates.py` (spec and payload building), `whatsapp_template_guard.py`, `huf/ai/whatsapp/outbound_policy.py`, `template_plain.py`, DocType `WhatsApp Template State`.
Happiol files: `loyal_arrow/huf_adapter/{templates,template_status,template_status_store}.py`, `loyal_arrow/api/templates.py`.

## How Huf works today

- `bridge.sync_templates(account)` reads Meta, imports or refreshes `WhatsApp Templates` rows, and upserts `WhatsApp Template State` (status, category, previous and correct category, rejection reason, quality). It is called from the admin API (`management.sync_templates`), credential setup, and one internal bridge caller. No scheduler entry calls it.
- Webhooks (status, quality, category) update `WhatsApp Template State`, pause affected broadcasts, and are forwarded to frappe_whatsapp.
- The send gate (`outbound_policy.check_template`) reads `status` from the `WhatsApp Templates` row, not from `WhatsApp Template State`.

## Capability comparison

Equivalents are "same purpose", not same signature. PARTIAL means some of the behaviour is missing.

### `template_status.py`

| Happiol function | Huf equivalent |
|---|---|
| `_` | `frappe._` (framework) |
| `_aware` | `_parse_ts` / `_utcnow` (bridge) |
| `is_fresh` (24 h TTL) | MISSING. `last_meta_update` is stored but never used to gate a send |
| `build_snapshot` | `_record_state_from_meta` -> `record_template_state` (no sync timestamp of its own; uses `last_meta_update`) |
| `effective_status` (STALE / UNKNOWN) | MISSING |
| `is_sendable` (exactly APPROVED and fresh) | PARTIAL: `check_template` tests APPROVED only, case-insensitive, no freshness, empty status allowed |
| `fresh_statuses` | MISSING |
| `plain_state` | PARTIAL: `template_plain.not_editable_text` words only the "cannot edit" case |
| `plain_states` | MISSING |
| `sync` (never raises, keeps previous snapshot on failure) | PARTIAL: `sync_templates` returns a structured error and keeps existing rows, but they never age out |
| `graph_rows` | `sync_templates` reads the Graph listing directly (`SYNC_FIELDS`) |
| `make_gateway_lister` | Not needed: Huf has the real listing |

### `template_status_store.py`

| Happiol function | Huf equivalent |
|---|---|
| `_naive_utc` | `frappe.utils.now_datetime` |
| `load_snapshot` (read error = nothing sendable) | PARTIAL: `_state_row` reads one row; it is not used by the send gate |
| `_norm_category` | PARTIAL: category is stored as received |
| `_cap` | PARTIAL: `state_key` and rejection reason are length-capped |
| `_upsert` | `record_template_state` |
| `run_sync` | `sync_templates` |
| `sync_from_meta` (coded token blockers) | PARTIAL: `sync_templates` returns `no_account` / `sync_failed`; no separate expired-token precheck |
| `sync_job` (hourly) | MISSING |

### `templates.py`

| Happiol function | Huf equivalent |
|---|---|
| `TemplateError` | `BridgeError`, `OutboundRefused` |
| `_read_entries`, `load_template_defs` (file registry) | No file registry; Huf's registry is `WhatsApp Templates`, `WhatsApp Template Draft` and `WhatsApp Template Extra`. App-owned content, stays in Happiol |
| `placeholders` | `whatsapp_templates.placeholders` (and `variables`, including named) |
| `_component`, `body_text`, `header_format` | `components_to_view`, `_template_view` |
| `expected_param_count` | `broadcast/checks/template_check.template_requirements` |
| `render_preview` | PARTIAL: send parameters are validated (`build_send_components`, `send_problems`); no confirmed public text preview helper |
| `definition_problems` | `validate_template_spec` (the `loyal_arrow_` name prefix rule is app-specific) |
| `normalise_status` | PARTIAL: upper-cased; `TEMPLATE_STATUSES` list, no explicit UNKNOWN mapping |
| `is_sendable_status`, `check_sendable` | PARTIAL: `check_template` (see gaps 1 and 2). No structural refusal of carousel needed: Huf can send carousels |
| `reconcile_statuses` (absent from listing = UNKNOWN; duplicate rows: non-approved wins) | MISSING: a template deleted at Meta keeps its last local status after sync |
| `validate_customer_app_domain`, `_resolve_button`, `resolve_buttons`, `load_button_settings` | App-specific (customer app URL, Stop button); stays in Happiol. Generic button building is `build_meta_components` |

### `api/templates.py`

| Happiol endpoint | Huf equivalent |
|---|---|
| `get_status` | `management.list_templates` / `get_template` (no freshness or token state in them as far as audited) |
| `submit` | `management.create_template` and the draft approve flow |
| `sync_status` | `management.sync_templates` |

### Asked-for capabilities

| Capability | Huf |
|---|---|
| Approval status sync | Present (manual sync and webhooks); not periodic |
| Category | Present, richer than Happiol (previous and correct category) |
| Quality score | Present in Huf (Happiol has none) |
| Freshness / staleness gate | Missing |

## Gaps that matter for `send.message` (G5)

1. **Unknown template passes.** `check_template` returns when the row is `None`, and allows an empty `status`. G5 needs "not exactly APPROVED = blocked".
2. **No staleness limit.** A row synced long ago and still `APPROVED` is sendable; with no scheduled sync, a missed webhook is never corrected.
3. **Two status stores.** Webhooks update `WhatsApp Template State` directly, while the gate reads `WhatsApp Templates.status`. The latter changes through sync or through the forward to frappe_whatsapp. That forward is best effort; frappe_whatsapp's handler was not inspected (its source was not found on the `hf-huf` bench or the v16 master). A `PAUSED` state could therefore coexist with an `APPROVED` row.
4. **`FLAGGED` is not a state.** It is not in `TEMPLATE_STATUSES` (only `last_event` is set) and not in the broadcast pause list, although the `record_template_webhook` docstring says flagged templates pause broadcasts. Happiol treats `FLAGGED` as not sendable.
5. **Deleted at Meta.** Sync does not mark local templates that are absent from the listing.

These are findings from reading the code; none was reproduced on a bench.

## Follow-up tasks (not done here)

Each touches more than one function or a G5 path, so none was patched in this audit.

| Proposed | Scope | Size |
|---|---|---|
| F1 | In the H-W2-02 / H-W2-03 guard step, block unless the template row exists, status is exactly `APPROVED`, and State is not `PAUSED`, `DISABLED`, `REJECTED` or flagged. Test in `test_flow_send_message.py` | S |
| F2 | Freshness: configurable TTL on `last_meta_update` plus a scheduled `sync_templates` per account (hooks.py). Note that webhooks also move `last_meta_update`, including quality-only ones, so a dedicated `last_synced_at` is safer (`WhatsApp Template Extra` already has one) | M |
| F3 | Sync marks templates absent from the Meta listing as not sendable | S |
| F4 | Handle `FLAGGED` in state and broadcast pause | S |

## Acceptance status

- Gap list with Huf equivalent or MISSING: this document.
- "`send.message` rejects a template whose state is not APPROVED" (test): **not done**. No `send.message` backend exists on this base (H-W2-03 not merged). Carry it into H-W2-03 (F1).
