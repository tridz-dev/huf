# Flow builder test ids

Stable `data-testid` hooks for live UI journeys. Field names are the contract config keys
(`docs/flow/FIELD_CONTRACT.md`). `<type>` is the contract node type (`trigger.webhook`, `agent.run`,
`tool.call`, `router.llm`, `condition`, `foreach`, `human.approval`, `transform`, `state.get`, `state.set`,
`state.delete`, `doc.create`, `output`).

## Toolbar and page
| Test id | Element |
|---|---|
| `flow-new` | New flow button (list header) |
| `flow-list-item-<flowId>` | Flow card on the list page |
| `flow-sidebar-item-<flowId>` | Flow entry in the left sidebar |
| `flow-canvas` | Canvas root |
| `flow-save`, `flow-run`, `flow-publish`, `flow-runs`, `flow-settings` | Toolbar buttons. `flow-publish` is disabled, with the reason in the `disabled-reason` tooltip, for a user without `flows.publish_sensitive` when the flow has a Data trigger or a web request step |
| `flow-save-state` | Saved / Unsaved indicator |
| `flow-validation-summary` | "N steps to finish" button beside "Saved" (only while something is unfinished). Opens the checklist `flow-issues-popover`; Run and Publish open it too instead of failing |
| `flow-add-trigger` | Add trigger button (when the flow has no trigger) |
| `flow-rail-trigger`, `flow-rail-agent`, `flow-rail-condition`, `flow-rail-tool`, `flow-rail-data` | Left palette rail |

## Palette modal
`flow-trigger-modal`, `flow-action-modal`, `flow-modal-add-trigger`, `flow-modal-cancel`.
Trigger modal: one list of cards (no tab bar, no search); the chosen card has `data-selected="true"` and a check `flow-card-check-<id>`; hint line `flow-trigger-hint` always takes its space. Empty trigger: card button `flow-node-choose-trigger-<nodeId>` and side-panel button `flow-trigger-choose` (panel `flow-trigger-unset`) both open `flow-trigger-modal`.
Cards: `flow-card-<id>` with ids
`webhook`, `schedule`, `doc-event`, `gateway`, `whatsapp`, `telegram` (triggers) and
`agent-run`, `tool-call`, `router`, `condition`, `loop`, `human.approval`, `transform`, `state-get`,
`state-set`, `state-delete`, `doc-create`, `email`, `http-request`, `file`, `slack`, `sheets` (steps), and `code-run` (Execute code: only offered when the server allows code in Flows and the user holds `flows.execute_code`, see wp19 below).
Card title = node title = sidebar title (derived from `data/actions.ts` / `data/triggers.ts`).

## Canvas nodes
| Test id | Element |
|---|---|
| `flow-node-<nodeId>` | Node wrapper (`data-node-type`, `data-incomplete="true|false"`) |
| `flow-node-title-<nodeId>` | Node title |
| `flow-node-subtitle-<nodeId>` | One line saying what the step does ("Send a message to #alerts"); full text in the tooltip |
| `flow-node-status-<nodeId>` | The card's ONE status word (`data-status`: ready, needs-setup, not-connected, orphan, running, waiting, done, failed, skipped). Under 80% zoom it is a coloured dot with the same test id and `aria-label`. Never wraps; cards are the same size in every state |
| `flow-node-incomplete-<nodeId>` | Inner text of the status word when it is "Needs setup" |
| `flow-node-marker-<nodeId>` | "Trigger" / "End" marker on trigger and end cards |
| `flow-node-choose-trigger-<nodeId>` | "Choose a trigger" button on the empty trigger card (title "Choose what starts this flow") |
| `flow-node-delete-<nodeId>` | Delete button (on the selected node) |
| `flow-node-delete-dialog`, `flow-node-delete-confirm` | Confirmation for configured nodes |
| `flow-handle-<nodeId>` | Single source handle |
| `flow-handle-in-<nodeId>` | Incoming (target) handle: drop a connection here |
| `flow-handle-<nodeId>-<route>` | Branch handle: `true`, `false`, `approve`, `reject`, `timeout`, `body` |
| `flow-add-step-<nodeId>` | Add-step card after a plain step |
| `flow-add-step-<nodeId>-<route>` | Add-step card for a branch (`true`, `false`, `approve`, `reject`, `body`, `option`, `timeout`) |
| `flow-insert-step-<edgeId>` | "+" on an edge |
| `flow-node-title-<nodeId>` / `data-lod` | The title; the card element carries `data-lod` = `full` (zoom 80% and up: icon, title, subtitle, status word), `compact` (50% to under 80%: icon, enlarged title, status dot) or `icon` (under 50%: an icon tile; the title shows on hover or focus in `flow-node-hover-<nodeId>`) |
| `flow-node-hover-<nodeId>`, `flow-node-run-summary-<nodeId>` | Note under a card on hover/focus: the title of an icon tile and, with a run shown on the canvas, one line of what the step produced (or why it failed) |
| `flow-run-overlay-chip`, `flow-run-overlay-hide` | "Showing this run" chip (top-left of the canvas) while a run is drawn on the canvas, and its Hide button. A run opened from history or `?run=<id>` stays drawn after the details close, until Hide, another run, or another flow |
| `data-run="taken"/"untaken"` on `flow-edge-label-<edgeId>` | A connection the shown run went along (green line) or not (faded) |
| `flow-edge-label-<edgeId>` | Branch name pill on a connection (Yes/No, Approved/Rejected/Timed out, For each item/When done, a router path in full, Next item on the loop-back line); 12px on screen at any zoom |

## Right sidebar (step panel frame, UX-8)
The panel is `components/RightSidebar.tsx` + `components/flow/frame/*`. A step's name appears ONCE, in the header input.

| testid | Where |
|---|---|
| `flow-config-sidebar` | Panel root. `flow-view-only-banner` for view-only people; `flow-sidebar-empty-hint` when nothing is selected |
| `flow-step-frame` (`data-step-kind`) | The open step: header, status strip, tabs, body |
| `flow-sidebar-header` | 56px sticky header: icon, name, kind, `...` menu, close |
| `flow-node-title-input` | The step name (editable in place; the only place the name is shown or typed). `flow-sidebar-title` no longer exists |
| `flow-sidebar-kind` | Small grey kind under the name ("Trigger", "End", "If / else") |
| `flow-step-info`, `flow-config-hint` | The (i) beside the kind and its popover with the longer explanation of the step |
| `flow-step-menu`, `flow-step-menu-content`, `flow-step-duplicate`, `flow-step-copy`, `flow-step-disable`, `flow-sidebar-delete` | `...` menu: Duplicate (not on a trigger), Copy, Disable / Turn on (linear action steps only), Delete (red); Duplicate and Copy show their keyboard hint. A disabled step has `data-disabled="true"` on its card |
| `flow-sidebar-close` | Close (panel variant only; the phone sheet has its own) |
| `flow-status-strip` (`data-state` = `todo`/`ready`/`off`) | 36px strip: "2 things to finish >" (amber button; jumps to the first one and focuses it) or "Ready" |
| `flow-sidebar-tabs`, `flow-sidebar-tab-setup`, `flow-sidebar-tab-test`, `flow-sidebar-tab-settings` | Tabs. Triggers: Setup + Test. End: no tabs (Setup only). `flow-sidebar-tab-<name>-dot` = something to finish in that tab (always Setup for required fields) |
| `flow-tab-setup`, `flow-tab-test`, `flow-tab-settings` | The three bodies (all stay mounted; inactive ones are `hidden`) |
| `flow-connection-needed`, `flow-connect-link-sidebar`, `flow-not-connected-sidebar`, `flow-connection-ok` | Top of Setup for integration steps: amber "Connect X to use this step" with a Connect button, or a calm "X is connected" |
| `flow-node-orphan-note` | Setup note when nothing leads to the step |
| `flow-more-options`, `flow-more-options-toggle` | Folded optional settings (`data-state` open/closed). Opens by itself when one has a value or when a field inside is jumped to |
| `flow-step-test` (root, `data-effect`), `flow-step-test-loading`, `-load-error`, `-retry`, `-viewonly`, `-ai-note`, `-ai-confirm` (+ `-yes`, `-no`) | Test tab states: loading, load error, view only (no server data), AI model note and the one-time confirm |
| `flow-step-test-input`, `-part-<key>`, `-part-empty-<key>`, `-source-<key>` (`data-source`), `-source-edited`, `-value-<key>-*`, `-no-input` | "Sample input": one block per source (`input`, a step id, `item`) with its chip (From last run / From pinned sample / From trigger sample / Edited sample) |
| `flow-step-test-edit`, `-reset`, `flow-json-step-test-sample-*`, `-sample-problem` | "Edit as JSON" (JsonArea) and its problem line |
| `flow-step-test-run` (`data-simulated`), `-hint`, `-running`, `-run-error`, `-save-note` | The Test step / Test (simulated) button, its one-line explanation, progress, errors |
| `flow-step-test-result` (`data-status`, `data-mode`), `-status`, `-simulated`, `-duration`, `-summary`, `-branch`, `-goes-to`, `-output-*` (HumanValue + `-raw-toggle`), `-shortened` | Result |
| `flow-step-test-error`, `-fix`, `-open-setup` | Failed test: readable error, how to fix it, jump to Setup |
| `flow-step-test-approval`, `-approval-title`, `-approval-facts`, `-approval-who` | Approval card preview |
| `flow-step-pin`, `flow-step-pinned`, `flow-step-unpin`, `flow-step-pin-area`, `flow-step-pinned-only`, `flow-step-pinned-value-*` | Pin this output / "Pinned 5 min ago" / Unpin |
| `flow-step-test-wait`, `-waiting`, `-last`, `-not-live`, `-docs`, `-doc-list`, `-doc-<name>`, `-tick`, `-trigger-sample`, `-trigger-empty`, `-trigger-note`, `-trigger-unset`, `-no-doctype` | Trigger Test tab: Wait for a test request, Use last received request, Pick a recent document, Simulate a tick |
| `flow-settings-on-failure`, `flow-on-failure-value`, `flow-step-notes`, `flow-step-reference-name`, `flow-view-as-json` (the collapsed "Advanced" disclosure), `flow-view-as-json-toggle`, `flow-view-as-json-text` (read-only JsonArea `flow-json-step-stored-*`) | Settings tab. The step's time limit lives here too: `flow-field-tool.call-timeout_ms` (connected tools only), `flow-field-human.approval-timeout_ms` |
| `flow-trigger-type`, `flow-trigger-change` | Trigger row at the top of a trigger's Setup. Both exist only once a trigger is chosen; an unset trigger shows `flow-trigger-unset` / `flow-trigger-choose` instead. `flow-hint-trigger-type` was removed |
| `flow-edge-config`, `flow-edge-meaning`, `flow-edge-label`, `flow-delete-confirm`, `flow-delete-cancel` | Connection panel and delete dialog |
| `flow-branches`, `flow-branch-<route>`, `flow-branch-<route>-empty` | "Where each path goes" |

Checklist (header "Saved . 3 steps to finish"): `flow-validation-summary` (button), `flow-issues-popover`, `flow-issues-title`, `flow-issues-note` (draft: "Your changes are saved ..."; live flow: "has to be finished before it can be saved"), `flow-issues-list`, `flow-issues-step-<nodeId>`, `flow-issues-row-<nodeId>-<field>`, `flow-issues-fix-<nodeId>-<field>` ("Fix": selects the step, opens the tab, scrolls to and focuses the field). Saving never blocks except for a live flow; Run and Publish open this list instead of a toast.

## Fields: `flow-field-<type>-<field>`, errors: `flow-error-<type>-<field>`
Dropdown options inside Selects: `flow-option-<name>`; Combobox options: `<field testid>-option-<value>`.

| Type | Fields |
|---|---|
| `trigger.webhook` | `url` (read-only address), `secret` (read-only, masked `****c3e6` until Show; `data-masked`), `flow-webhook-url-text` (the address as shown, wrapping only at / . ? =), `method` (options `flow-option-webhook-method-GET|POST`) |
| | buttons `flow-webhook-copy-url`, `flow-webhook-copy-secret`, `flow-webhook-secret-toggle` (Show for 30 s / Hide), `flow-webhook-regenerate` (opens `flow-webhook-regenerate-dialog` with `-cancel` / `-confirm`); note `flow-webhook-secret-new-note`; pill `flow-webhook-live`; panel `flow-webhook-panel` |
| | data it sends: `flow-webhook-data`, `flow-webhook-fields` / `flow-webhook-field` (plain rows), buttons `flow-webhook-paste-sample`, `flow-webhook-use-last`, `flow-webhook-clear-sample`, JSON area `flow-json-webhook-sample` (`-input`, `-help`, `-copy`, `-format`, `-error`), `flow-webhook-sample-save` / `-cancel`, `flow-webhook-sample-note` |
| | developer reference (closed until opened): `flow-webhook-usage` (`data-open`), `flow-webhook-howto-toggle`, `flow-webhook-howto`, JSON area `flow-json-webhook-body` (title "Request body (JSON)"), command `flow-webhook-usage-curl` with `flow-webhook-usage-curl-copy`, `flow-webhook-usage-secret-note`, `flow-webhook-responses` |
| `trigger.schedule` | `frequency` (options `flow-option-schedule-frequency-<minutes|hours|daily|weekly|monthly|custom>`), `every` (options `flow-option-schedule-every-<n>`), `minute` (hours only), `time` (daily, weekly, monthly), `weekday` (group) with `weekday-<0..6>` buttons and presets `flow-schedule-preset-<weekdays|weekend|everyday>`, `monthday` (options `flow-option-schedule-monthday-<1..31|last>`), `zone` (time zone; options `flow-field-trigger.schedule-zone-option-<IANA name>`), `cron` (only under Custom); `flow-schedule-preview` wraps `flow-schedule-summary` (sentence), `flow-schedule-timezone` (how the time shows in the browser) and `flow-schedule-next-runs` / `flow-schedule-next-run` |
| `trigger.doc-event` | `doctype` (searchable list, `-search`, options `flow-field-trigger.doc-event-doctype-option-<name>`), `event` (options `flow-option-doc-event-<event>`); sentence `flow-data-sentence`, panel `flow-data-trigger`, `flow-doc-event-filter` (the "Only when... coming soon" note) |
| trigger panel | `flow-trigger-apply`, `flow-trigger-clear`, `flow-trigger-disabled-reason` |
| `agent.run` | `agent`, `prompt`, `prompt_bindings`; `flow-binding-<name>`; picker `flow-agent-run-variable-picker` (+ `-item-<ref>`) |
| `tool.call` | `tool_id`, `input.<key>` (e.g. `input.to`, `input.subject`, `input.body`, `input.channel`, `input.text`, `input.url`, `input.method`, `input.headers`, `input.body`); every value control is a `DataInput` (typed text and chips in one box; its "+ Use data" button is `flow-field-tool.call-input.to-picker`, see UX-9 below) |
| `router.llm` | `prompt`, `options` (list), `flow-router-path-label-<targetNodeId>`, `flow-router-path-<targetNodeId>`, `flow-router-no-paths`, `default` |
| `condition` | `expression`; branches `flow-branch-true`, `flow-branch-false` |
| `foreach` | `items`, `max_iterations`, `on_item_error` (`flow-option-loop-on-error-fail|skip`), `collect`; branches `flow-branch-body`, `flow-branch-next`; pickers `flow-loop-items-picker`, `flow-loop-collect-picker` |
| `human.approval` | `message`, `approver_type` (required; `flow-option-approver-role|user`; inline error `flow-error-actionConfig-approver_type`), `approver_role`, `approver_users`, `timeout_ms` (minutes in the UI); branches `flow-branch-approve|reject|timeout` |
| `transform` | `op` (`flow-option-transform-op-<op>`), `input.<param>` |
| `state.get|set|delete` | `key`, `default`, `value`, `ttl_seconds` |
| `doc.create` | `doctype`, `fields.<i>.name`, `fields.<i>.value`, `fields.add` |
| `output` | `flow-field-output-value` |

Validation messages: `flow-error-<type>-<field>` (role="alert"). They are hidden on a form nobody has touched; a field's message appears after the person has been in the field and left it, when "Fix" or the status strip sends them there, or never otherwise. There is no banner above the form (`flow-node-incomplete` is gone) and no toast: one place per error.

## Variable picker
Every text/value input has an "Insert data" picker listing the trigger (`input`, `trigger`), the steps that always run before the step (node ids) and, inside a loop, `foreach.item` / `foreach.index`. Later steps and other branches are never listed.
Picker id = `<field test id>-picker`, items `<picker id>-item-<ref>`. Examples: `flow-field-tool.call-input.url-picker`, `flow-field-transform-input.text-picker`, `flow-field-condition-expression-picker`, `flow-field-router.llm-prompt-picker`, `flow-field-human.approval-message-picker`, `flow-field-output-value-picker`, `flow-binding-picker-<name>` (agent prompt data), `flow-agent-run-variable-picker`, `flow-loop-items-picker`, `flow-loop-collect-picker`.
Value inputs insert a reference (`$from`) or, after typed text, a `$template` with the variable; the condition expression gets the name (`node_1` or `input`); the router prompt and approval message get `{input}` / `{node_1.field}` placeholders (filled in at run time).

## Integrations and tool steps
| Test id | Element |
|---|---|
| `flow-not-connected-node-<nodeId>` | "Not connected" badge + Connect link on a step whose integration has no credentials |
| `flow-not-connected-sidebar`, `flow-connect-link-sidebar` | Same notice and link in the step settings (link goes to the real connect screen) |
| `flow-node-tool-<nodeId>` | Removed: the tool's plain name is now the card subtitle (`flow-node-subtitle-<nodeId>`) |
| `flow-field-tool.call-timeout_ms` | "Wait up to" (seconds) |
| `flow-field-router.llm-model`, `flow-option-router-model-default`, `flow-option-router-model-<modelName>` | Router AI model (optional) |
| `flow-toggle-panels`, `flow-open-settings` | Canvas corner buttons |

Publishing a flow with unconnected integration steps shows a warning toast (`Some steps are not connected yet`); it never blocks.

## Runs, run details, settings, approvals
| Test id | Element |
|---|---|
| `flow-run-history`, `flow-run-history-refresh`, `flow-run-row-<runId>` (`data-run-status`) | Runs sheet |
| `flow-run-details`, `flow-run-current-node`, `flow-run-error`, `flow-run-approve`, `flow-run-reject` | Run details sheet; the open run is in the URL as `?run=<id>` |
| `flow-run-meta`, `flow-run-flow-name`, `flow-run-trigger`, `flow-run-started`, `flow-run-finished`, `flow-run-duration`, `flow-run-decision-<nodeId>`, `flow-run-step-error-<nodeId>` (reason on a failed step card), `flow-run-step-output-<nodeId>` (step output, step ids shown as titles) | Run details facts and recorded approval decision |
| `flow-run-stale`, `flow-run-mark-failed`, `flow-run-mark-failed-confirm` | Stuck-run notice and System Manager "Mark as failed" |
| `executions-tab-flow-runs`, `flow-runs-table`, `flow-run-exec-row-<runId>` (`data-run-status`), `execution-flow-label-<agentRunId>`, `executions-runs-tile` | Executions page: Flow runs tab and flow-step labels |
| `flow-settings-modal`, `flow-settings-name`, `-description`, `-category`, `-auto-convert`, `-save`, `-cancel`, `-delete` | Settings modal |
| `flow-approvals-bell`, `flow-approvals-count`, `flow-approvals-panel`, `flow-approval-<runId>`, `flow-approve-<runId>`, `flow-reject-<runId>`, `flow-approval-flow-<runId>`, `flow-approval-message-<runId>`, `flow-approval-time-<runId>` | Approvals bell |
| `flow-run-dialog`, `flow-run-advanced` (flows that declare no fields: the link that reveals the JSON box), `flow-run-start` (label `Run test` / `Run for real`), `flow-run-cancel` | Run dialog opened by the Run button and the list card Run action |
| `flow-run-mode`, `flow-run-mode-test`, `flow-run-mode-real` (radio, `data-state`), `flow-run-mode-test-card`, `flow-run-mode-real-card`, `flow-run-real-warning` | Run dialog: Test run (default) / Run for real and the warning shown for a real run |
| `flow-run-form`, `flow-run-field-<field>` (`.` becomes `-`), `flow-run-use-last`, `flow-run-use-sample`, `flow-run-note`, `flow-run-loading`, `flow-run-payload-hint` | Run dialog: the form generated from the trigger's declared fields, 'Use last real request', 'Use sample' |
| `flow-json-run-payload`, `-input`, `-toggle`, `-error`, `-format`, `-copy` (JsonArea) | Run dialog: the JSON view of the same details ('Edit as JSON' / 'Show as form'); replaces the old `flow-run-payload` (the box) and its syntax error |
| `flow-run-payload-error` | Run dialog: text that is valid JSON but not an object ('The input must be a JSON object'); the JSON area's own message covers broken JSON |
| `flow-run-test-chip-<runId>` | Grey 'Test' chip in the Runs sheet |
| `disabled-reason` | Wrapper around a control disabled for a view-only user; hover/focus shows the explanation |
| `connection-indicator` (`data-status` = connecting / connected / offline) | Header dot for the live-updates connection |

## Connections, step removal, publish state (wp7)
| Test id | Element |
|---|---|
| `flow-edge-line-<edgeId>` | The hit area of a connection (click it away from the + to select the line; it is highlighted) |
| `flow-edge-remove-<edgeId>` | "Remove connection" button (28px, tooltip) on the selected line |
| `flow-edge-controls-<edgeId>` | The "+" / remove buttons of a line (shown on hover or when selected) |
| `flow-edge-from`, `flow-edge-to` | Step chips of the connection panel (click selects that step) |
| `flow-edge-kind` | Pill naming the kind of connection ("If Yes", "Loop: for each item", "Loop: when done") |
| `flow-edge-ends` | The From -> To row of the connection panel |
| `flow-edge-panel-insert`, `flow-edge-panel-remove` | "Add a step here" / "Remove connection" in the connection panel |
| `flow-edge-delete-dialog`, `flow-edge-delete-confirm` | Confirmation shown by that button and by the Delete key on a selected line |
| `flow-edge-config` | Sidebar "Connection" panel of the selected line |
| `flow-node-orphan-<nodeId>` | "Nothing leads here" status word on a step no trigger reaches |
| `flow-delete-mode`, `flow-delete-mode-reconnect`, `flow-delete-mode-cascade` | Choice in the step delete dialog (`flow-node-delete-dialog`) when the step has a step after it: "Remove step and reconnect" (default) / "Remove step and everything after it" |
| `flow-published-badge`, `flow-draft-badge`, `flow-status-pill`, `flow-unpublish`, `flow-unpublish-dialog`, `flow-unpublish-confirm` | Header status: wrapper `flow-published-badge` while Live (`flow-draft-badge` while not) around the shared pill `flow-status-pill` (Draft / Live / Has problems); Unpublish replaces Publish while the flow is live |
| `status-pill-<kind>` | Default test id of the shared `StatusPill` (`data-status` = kind: draft, live, has_problems, archived, queued, running, waiting_approval, waiting_review, finished, failed, stuck, approved, rejected, timed_out) |
| `flow-list-status-<flowId>` | Status pill on a flow's card in the list |
| `flow-run-document`, `flow-run-document-doctype`, `-name`, `-event`, `-fields`, `flow-run-full-payload` | Data trigger run: "Document" summary and the collapsed "Full payload" (`flow-run-input` is inside it) |
| `flow-doc-event-reset-note` | Message shown when changing the document type cleared an event that type cannot have |
| `boot-fallback`, `app-error-screen`, `chunk-error-screen` | "Something went wrong / Reload" screens (entry script, app crash, page chunk) |
| `flow-run-document-value-<field>`, `flow-run-document-more-<field>` | Data trigger run: a long document field (HTML shown as plain text) and its "Show more" / "Show less" button |
| `flow-run-step-connect-<nodeId>` | "Connect" link in a failed step card whose reason is "<Integration> is not connected" |
| `agent-run-source`, `agent-run-flow-run-link` | Agent run details of a flow step: "Flow: <flow name> > <step title>" heading text and the link to the Flow Run |
| `flow-tidy-layout` | Canvas toolbar "Tidy layout" button (lines the steps up; toast has Undo) |

## Integration set-up help (wp12)
| Test id | Element |
|---|---|
| `integration-setup-guide`, `integration-setup-steps`, `integration-setup-scopes` | Numbered how-to and the exact permissions, on the Integration screen for Gmail, Slack, Google Sheets and Google Drive |
| `integration-test-connection` | "Test connection" button in the page header (read-only check; typed values are used when filled in, otherwise the saved ones). Disabled on a new integration until a credential is typed |
| `integration-test-result` (`data-status` = connected / attention / not_connected / inactive / unchecked) | The one status sentence under the title: what the last check said and when |
| `flow-step-<kind>-input.<field>-hint` | One-line "where do I find this" under a tool input (Slack channel, Sheets and Drive IDs) |

## Integrations health (UX-7)
| Test id | Element |
|---|---|
| `integration-card-<name>` (`data-status`) | One connection card on /integrations; `integration-card-title` friendly name, `integration-card-detail` the one status sentence |
| `integration-status` (`data-status` = connected / attention / not_connected / inactive / unchecked / active) | The single status pill (cards, page header, inactive rows) |
| `integration-use-in-agent-<name>`, `integration-open-<name>` | Card buttons "Use in agent" and "Fix this" / "Settings" |
| `integration-use-in-agent` | Header button on the details page (same verb for channels) |
| `integration-inactive-groups`, `integration-group-<service>` | Collapsed "Not in use" section that groups identical inactive copies per service |
| `integration-category-filter` | "All categories" dropdown (integrations list, service catalog) |
| `integration-header`, `integration-title`, `integration-save` | Details page header, friendly title, Save/Create |
| `integration-status-line`, `integration-fix-credentials`, `integration-last-problem` | Status line, "Add credentials" / "Update credentials" button that scrolls to and focuses the first empty credential, dismissible "Problem since the last check" |
| `integration-credentials`, `integration-name-input`, `credential-input-<key>`, `credential-state-<key>` | Name and credentials section (first on the page); per-field Saved / Not set badge |
| `integration-setup-toggle` | "How to connect" accordion trigger (closed by default) |
| `integration-options` | Active and "Use by default" switches |
| `settings-skill-sources-editor`, `skill-source-row-<n>`, `skill-source-add`, `skill-sources-json-toggle`, `skill-sources-json`, `skill-sources-json-error`, `settings-skill-sources-save` | Code and skills page: skill sources list editor, Edit as JSON toggle and area, Save |

## Slack channels and run summaries (wp16)
| Test id | Element |
|---|---|
| `flow-run-summary-<nodeId>` | One-line plain summary above a finished integration step's output (Posted to, Sent to, status from host, row/file counts) |
| `flow-run-raw-<nodeId>` | Collapsed "Show raw response" (`<details>`); the secrets-stripped output stays at `flow-run-step-output-<nodeId>` inside it |
| `slack-channels-loading`, `slack-channels-retry`, `slack-use-<name>` | Recipients tab channel list: loading line, Try again button after an error or timeout (15 s), "Save as recipient" row action. `slack-load-channels` is now the Reload button; the list loads when the tab opens |
| `slack-load-channels`, `slack-channels`, `slack-channel-list`, `slack-channel-<name>`, `slack-copy-id-<name>`, `slack-channels-error`, `slack-channels-empty` | Integration > Recipients tab (saved Slack integration): read-only "Load channels" list with copy-ID buttons |
| `flow-slack-channel-picker`, `flow-field-slack-channel-pick`, `flow-slack-channel-picker-error` | "Or pick a channel" searchable list under the Slack step's Channel field (only when Slack is connected) |

## Execute code in Flows (wp19)
Node type `code.run`, canvas type `code-run`, palette card `flow-card-code-run` (name "Execute code"; hidden while the switch is off or without `flows.execute_code`). Ids below are used as written (one Execute code form is open at a time).
| Test id | Element |
|---|---|
| `flow-code-editor` | Python code editor (textarea with a line-number gutter `flow-code-gutter`) |
| `flow-code-profile` | Profile select trigger (options `flow-option-code-profile-<name>`, default "Flow Scratch") |
| `flow-code-profile-badge` | "Needs approval each run" badge, shown only for a profile whose approval mode is not Auto Approve |
| `flow-code-timeout` | Time limit in seconds (capped at the profile's limit) |
| `flow-code-inputs-add` | Add input button |
| `flow-code-input-key-<i>`, `flow-code-input-value-<i>` | Name and value of input row `i` (value is a `DataInput`: `-picker` suffix as for other fields); remove with `flow-code-input-remove-<i>` |
| `flow-code-help` | "How your code runs" help (`<details>`) |
| `flow-code-readonly-note` | "You need permission to run code to edit this step." (the form is then disabled) |
| `flow-error-code.run-code`, `-profile`, `-timeout_s`, `-inputs` | Inline required-field errors |
| `flow-node-code-profile-<nodeId>` | Removed: the card subtitle says "Run a Python snippet" (the profile stays in the step settings) |
| `flow-code-output-exit` | Exit status badge in a step's output in Run details (inside `flow-run-step-output-<nodeId>`) |
| `flow-code-output-stdout`, `flow-code-output-stdout-empty` | Printed output block / "Nothing was printed." |
| `flow-code-output-result` | Result as formatted JSON (absent when the code returned nothing) |
| `flow-code-output-truncated` | "Output was cut off because it was too long." |
| `run-waiting-code-note` | Pending-actions line of a run in status "Waiting Code" (displayed "Waiting for code"; `data-run-status="Waiting Code"` on list rows): "Waiting for an administrator to approve this code run. Check the approvals bell." or "Running your code in a sandbox..." |
| `execution-approvals-bell`, `execution-approval-<name>`, `execution-approve-<name>`, `execution-reject-<name>` | Approvals bell (code runs waiting for a decision): the bell, one pending item (its heading reads "Flow: <flow> > <step>" for a Flow step), and its Approve / Reject buttons |
| `settings-code-in-flows` | "Code in Flows" card on Settings > Agent settings |
| `settings-code-in-flows-switch` | "Allow code execution in Flows" switch (disabled unless the user is a System Manager) |
| `settings-code-in-flows-status` | "Server switch: on" / "Server switch: off - ..." line |
| `settings-code-in-flows-note` | "Only a system administrator can change this." (non-admins) |

Publish is disabled (reason in `disabled-reason`) when the flow has an Execute code step and code is off or the user lacks `flows.execute_code`.

## Help text and guidance (wp17)

| Test id | Meaning |
|---|---|
| `flow-help`, `flow-help-popover`, `flow-help-shortcuts`, `flow-help-guide-link` | "?" button in the editor header, its popover (how a flow works, keyboard shortcuts) and the link to the full guide |
| `flow-first-run-guide`, `flow-first-run-guide-close` | Coach mark anchored to the trigger (`data-placement` beside-trigger or below) on a flow with only a trigger (hidden for view-only users; closing it is remembered in the browser) |
| `rf__minimap` (React Flow keeps its own id; the `flow-minimap` prop is overridden) | Overview map, bottom-left of the canvas (hidden under 8 steps and when the canvas is narrower than 640px) |
| `flow-palette-intro` | One-sentence intro under the "Choose what starts this flow" / "Add a step" title |
| `flow-palette-empty` | Empty state of the palette search ("No steps match ..."), with `flow-palette-clear-search` ("Show all") |
| `flow-palette-section-<category>` | A labelled palette section: agent (AI), control (Decide and repeat), people, data (Work with data), apps, advanced |
| `flow-transform-group-<section>` | Labelled group in the Transform operation list: change-text, find-in-text, pick-rows, group-combine, values |
| `flow-card-desc-<cardId>` | The one-line "what does this step do" under a palette card |
| `flow-config-hint` | Intro sentence of a step or trigger, inside the (i) popover in the panel header |
| `flow-hint-<form>-<field>` | One-line hint under a field (for example `flow-hint-webhook-secret`, `flow-hint-loop-max`, `flow-hint-approval-timeout`, `flow-hint-transform-op`, `flow-hint-transform-example`, `flow-hint-condition`) |
| `<field testid>-hint` | Hint under a value input (URL, Subject, Spreadsheet ID ...) |
| `flow-condition-examples`, `flow-schedule-examples`, `flow-doc-event-explained` | Folded example lists (condition syntax, cron examples, what each Data event means) |
| `flow-webhook-responses` | What 200 / 403 / 405 / 429 mean (inside the closed-by-default developer reference) |
| `flow-hint-schedule-intro`, `flow-hint-schedule-every`, `flow-hint-schedule-monthday`, `flow-hint-schedule-zone`, `flow-hint-schedule-cron` | Schedule intro and field help |
| `flow-hint-doc-event-intro`, `flow-hint-doc-event-doctype`, `flow-hint-doc-event-event` | Data trigger help |
| `flow-sidebar-empty-hint` | Sidebar help lines (the Step name help and the "Steps after this one" footer were removed) |
| `flow-settings-name-hint`, `flow-settings-description-hint`, `flow-settings-category-hint` | Settings dialog hints |
| `flow-run-payload-hint` | Run dialog help under the input box |
| `flow-run-history-header`, `flow-run-history-body`, `flow-run-history-timezone` | Sticky header, scrolling body and time zone note of the Runs sheet |
| `flow-run-details-header`, `flow-run-details-body`, `flow-run-timezone-note` | Same for Run details |
| `flow-view-only-pill`, `flow-view-only-pill-hint` | "View only" pill beside the flow name in the editor header (people who cannot edit the flow; tooltip on hover and focus) |
| `flow-webhook-secret-hidden` | "Hidden. Ask a flow editor." in place of the secret, Show, Copy and Make a new secret for people who cannot edit the flow; none of `flow-webhook-copy-secret`, `flow-webhook-regenerate`, `flow-webhook-secret-toggle`, the paste / use-last buttons or the secret input exist for them |
| `flow-settings-view-only`, `flow-settings-name-value`, `flow-settings-description-value`, `flow-settings-category-value`, `flow-settings-close` | Read-only flow settings (no Save, Cancel, Delete or inputs) |
| `flow-run-history-empty` | Empty Runs sheet; the text for view-only users has no "Press Run" |
| `flow-not-connected-note-<suffix>` | "A flow editor needs to connect X" shown instead of the Connect link to view-only users |
| `settings-skill-sources`, `settings-skill-source-<name>`, `settings-skill-sources-empty`, `settings-skill-sources-error` | Read-only skill sources on Agent settings (people who are not system administrators; there is no JSON box and no Save destinations) |

## UX-2 humanize core (HumanValue, JsonArea, friendly run title)
| testid | Where |
|---|---|
| `flow-run-title` (`data-run-id`) | Run details header: "Run #N · <flow name>" (never the internal id) |
| `flow-run-human-<nodeId>` | A step's output as labelled rows (HumanValue root); `flow-run-human-input` for the data a run started with |
| `<root>-row-<path>`, `<root>-label-<path>`, `<root>-value-<path>` | One labelled row of HumanValue; `<path>` is the dotted key path (`customer.name`, `lines.0.qty`) |
| `<root>-list-<path>` (+ `-toggle`, `-count` "N items", `-items`, `-item-<i>`, `-show-more`) | A list: collapsed "N items · first few", opens to one card per item |
| `<root>-text-<path>` (+ `-more`) | Long text folded to a preview with Show more / Show less |
| `<root>-empty`, `<root>-raw-toggle` | Empty text; the "{ } Raw" control (`aria-expanded`); the raw JSON area opens below it |
| `flow-run-received-<nodeId>` | "Data received" caption: the run's trigger input shown inside the first step instead of a second block |
| `flow-run-trigger-input`, `flow-run-input-empty` | Separate "Data this run started with" block (only when no step repeats it) and its "No data was sent" line |
| `flow-run-step-output-<nodeId>`, `flow-run-input` | Now the RAW JSON text, present only after "{ } Raw" is opened (HumanValue is the default view) |
| `flow-json-<key>`, `-input`, `-format`, `-copy`, `-error`, `-toggle`, `-more`, `-help`, `-text` | JsonArea (the one component for legitimate JSON): `-toggle` is "Show as form" / "Edit as JSON", remembered per key; `-more` folds over 12 lines |
| `flow-run-waiting-user`, `flow-run-human-waiting`, `flow-json-run-resume` (+ `-input`, `-error`, `-format`, `-copy`), `flow-run-resume` | Run waiting for someone to continue: its facts as labelled rows and the optional "extra information (JSON)" area; `flow-run-resume` is the Continue button (off while the JSON is invalid) |

## UX-11 / UX-20 flows list, new-flow chooser, publish and settings dialogs
| testid | Where |
|---|---|
| `flow-list-item-<flowId>` | Flow card (whole card opens the flow). Inside it: `flow-card-title` (2 lines, `title` = full name), `flow-card-description`, `flow-card-trigger` ("Starts when ..."), `flow-card-last-run` (`data-run-status`), `flow-card-category` (only when set), `flow-card-steps` (icon strip), `flow-card-trigger-icon` (`data-trigger`) |
| `flow-card-open`, `flow-card-run`, `flow-card-menu`, `flow-card-menu-content`, `flow-card-duplicate`, `flow-card-settings`, `flow-card-delete` | Labelled card actions and the "..." menu (view-only people only get Open and the menu's "View settings") |
| `flow-list-filters`, `flow-list-search`, `flow-list-status-filter`, `flow-list-category-filter`, `flow-list-sort` (wide screens), `flow-list-filters-button` ("Filters (n)") + `flow-list-filters-sheet` with `flow-list-status-filter-sheet`, `-category-filter-sheet`, `-sort-sheet` (phone), `flow-list-limit-note`, `flow-list-error` | List filter row ("All statuses", "All categories", "Recently updated"), the "Showing N of M" note with Show more, load error |
| `flow-delete-dialog`, `flow-delete-name`, `flow-delete-confirm` | Delete confirmation opened from a card ("Delete this flow?") |
| `flow-first-run-coach`, `flow-first-run-start` | "Build your first flow" panel on an empty list, and its "Start with a template" button |
| `flow-new-dialog`, `flow-new-scratch`, `flow-template-<templateId>`, `flow-templates-<group>`, `flow-template-steps` | New flow chooser: start from scratch, one button per template (ids in `data/flowTemplates.json`), group sections, icon strip |
| `flow-publish-dialog`, `flow-publish-summary` (`data-start-kind`), `flow-publish-warnings`, `flow-publish-warning-unconnected`, `flow-publish-warning-problem`, `flow-publish-connect`, `flow-publish-cancel`, `flow-publish-confirm` | Publish summary: what will start the flow (+ web address with Copy for a webhook), warnings, confirm |
| `flow-settings-more`, `flow-settings-danger-zone`, `flow-settings-category-new`, `flow-settings-name-error`, `flow-settings-error` | Settings: collapsed "More" (holds `flow-settings-auto-convert`), Danger zone, new-category input, inline errors |
| `flow-settings-delete` (opens the in-dialog confirm), `flow-settings-delete-title`, `flow-settings-delete-cancel`, `flow-settings-delete-confirm` | Settings deletion: the confirm replaces the dialog body (no second dialog) |

## UX-23 responsive shell, phone steps list, roles
| testid | Where |
|---|---|
| `flow-page` (`data-layout` = `docked` / `sheet` / `phone`) | The editor page. `docked`: step panel beside the canvas; `sheet`: panel opens over it (canvas would drop under 520px); `phone`: under 768px |
| `flow-header-more`, `flow-header-more-menu`, `flow-status-pill-menu` | Header "..." menu at 1200px and narrower (and on a phone). It holds `flow-runs` (Run history), `flow-settings` (Flow settings), `flow-help`, `flow-tidy-layout`, `flow-convert-to-procedure` / `flow-saved-as-procedure`; on a phone also `flow-phone-view-toggle-menu` (Show map / Show steps) |
| `flow-name` | The flow name in the header (tooltip carries the whole name) |
| `flow-step-panel` (`data-width`), `flow-panel-resizer` | Docked step panel and its grab bar (role separator, 300-480, arrow keys, remembered) |
| `flow-step-sheet`, `flow-sheet-back` | Step settings as a sheet (under ~900px and on a phone) and its "Back to the flow" control; `flow-phone-read-only-note` on a phone |
| `flow-phone-banner`, `flow-phone-view-steps`, `flow-phone-show-map`, `flow-phone-map-bar` | Phone: the "Editing steps works best on a larger screen" note with View steps, and the Show map button in its own bar under the steps list |
| `flow-steps-list`, `flow-step-card-<nodeId>` (+ `-title-`, `-summary-`, `-status-`), `flow-step-branch-<nodeId>` | Phone steps list: one card per step in reading order (icon, title, one line, status); branch name above the first step of a branch |
| `flow-run-decision-bar`, `flow-run-decision-inline`, `flow-run-cannot-decide`, `flow-run-back` | Run details: sticky Approve / Reject bar on a phone, the inline pair elsewhere, the sentence shown to someone who may not decide, the "Runs" back button |
| `flow-approval-group-<firstRunId>`, `flow-approval-group-heading` | Bell: identical requests grouped under "3 waiting: Order approval" (every request keeps its own `flow-approve-<runId>` / `flow-reject-<runId>`) |
| `no-access-page`, `no-access-title`, `no-access-body`, `no-access-go-flows`, `no-access-go-hub` | "You don't have access to this page" (Hub, Flows, Executions, Settings, Agents, Dashboard) |

## UX-9 Use data picker, chips, preview (`components/flow/data/*`)
| testid | Where |
|---|---|
| `<field testid>` | The box of a `DataInput` (role textbox, contenteditable: typed text and chips). `fill` replaces everything; `value` / `value_matches` read its words (chips as "Customer > Name . New order"); the runner reads it with `readValue` |
| `<field testid>-picker` | "+ Use data" button inside the box's right edge (also the `VariablePicker` button of prompt, condition and loop fields) |
| `<field testid>-preview`, `-preview-text` | "What this will become: ..." line under a filled input that holds data, from examples; unknown parts read `[Customer name: no sample yet]` |
| `<field testid>-hint`, `-box`, `-not-a-number`, `-use-text` | Hint line, wrapper, number field error ("Enter a number"), "Use plain text instead" under a JSON area that was opened by an old list/object value |
| `<field testid>-yes`, `-no`, `-unset` | Options of a Yes/No field (`kind="yesno"`) |
| `flow-json-<field testid with . and _ as ->-input` | The Advanced (JSON) text of a `kind="json"` field (JsonArea key = testid lower-cased, non-letters to `-`) |
| `flow-use-data` | The picker panel (role dialog), beside the input; `flow-use-data-title`, `-back`, `-search` |
| `flow-use-data-step-<stepId>` | Level 1: one row per step the field can read (trigger first, closest step next); the loop's item row has id `<loopId>:item` |
| `flow-use-data-field-<path>` | Level 2: a field row (`path` is the reference, e.g. `input.customer.name`, `node_5.total`); `flow-use-data-sample` is its example text |
| `flow-use-data-each`, `-first`, `-joined`, `-count` | Level 3 of a list: Each item (use in a loop) / First item / All items, joined with commas / How many items |
| `flow-use-data-summary`, `-all`, `-result` | "Show as summary table" (object or first item), "Everything in X", "Its result" / "Everything this step produced" |
| `flow-use-data-nosample`, `flow-use-data-last-request`, `flow-use-data-empty` | "No sample yet: run a test" panel, its "Use last real request" button (webhook trigger), empty message |
| `flow-use-data-type-it`, `flow-use-data-typed` | "Can't find it? Type the field name" and its box (Enter inserts; `input.customer.name` or `customer.name` inside a step) |

## Run details as a story (UX-4)

| Test id | What |
|---|---|
| `flow-run-started-by` | "Started by you · 5:15 PM" under the title |
| `flow-run-headline`, `flow-run-headline-text`, `flow-run-headline-sub`, `flow-run-status` (StatusPill), `flow-run-outcome` (`data-tone`) | Outcome sentence, state pill from the one status set, outcome chip |
| `flow-run-timeline`, `flow-run-step-<id>` (`data-step-status` done/failed/waiting/stopped), `flow-run-step-phrase-<id>`, `flow-run-step-title-<id>`, `flow-run-decision-<id>` (one-line sentence of the step) | The step cards |
| `flow-run-human-<id>` (+ `-raw-toggle`), `flow-run-step-output-<id>` (raw data) | A step's labelled rows and its "{ } Raw" toggle |
| `flow-run-error` (exactly one per failed run), `flow-run-step-error-<id>`, `flow-run-fix-<id>` ("Fix this step", "Open this step" for read-only people), `flow-run-step-connect-<id>` | The one error and its actions |
| `flow-run-iterations-<loopId>`, `flow-run-iterations-toggle-<loopId>`, `flow-run-iterations-list-<loopId>`, `flow-run-children-<loopId>` | Loop: "N iterations", per-round results, body steps |
| `flow-run-waiting`, `flow-run-waiting-heading`, `flow-run-approval-facts`, `flow-run-waiting-since`, `flow-run-approve` / `flow-run-reject` | Waiting card above the steps |
| `flow-run-stale`, `flow-run-stuck-for`, `flow-run-mark-failed` ("Stop run"), `flow-run-mark-failed-confirm`, `flow-run-queued`, `flow-run-cancel` | Stuck banner, queued note, stop/cancel actions |
| `flow-run-details-fold` (`<details>`), `flow-run-details-toggle`, `flow-run-meta`, `flow-run-flow-name`, `flow-run-trigger`, `flow-run-started`, `flow-run-finished` (only when finished), `flow-run-duration`, `flow-run-step-count`, `flow-run-current-node`, `flow-run-id`, `flow-run-id-copy`, `flow-run-timezone-note` | "Details" fold (collapsed by default) |
| `flow-run-back` | "Run history" link back to the list |
| `flow-run-row-<runId>` (`data-run-status`), `flow-run-hist-title-<runId>`, `flow-run-hist-status-<runId>`, `flow-run-hist-outcome-<runId>`, `flow-run-hist-started-<runId>`, `flow-run-hist-hint-<runId>` | Run history rows |
| `executions-tabs`, `executions-tab-runs` ("Agent runs"), `executions-tab-flow-runs` ("Flow runs"), `executions-tab-analytics`, `executions-tab-hint`, `page-frame-tabs`; `flow-run-exec-row-<runId>`, `flow-run-exec-title-<runId>`, `flow-run-exec-status-<runId>`, `flow-run-exec-outcome-<runId>` | Executions page |

`useRunOverlay(runId)` (lib/flow-run/useRunOverlay.ts) returns `{ nodes: { [stepId]: { status: 'done'|'failed'|'waiting'|'stopped', summary } }, runStatus, currentNodeId, loading }` for the canvas.

## Keyboard, undo and the Cmd+K palette (UX-19)
| testid | What |
|---|---|
| `flow-history-buttons` (group), `flow-undo`, `flow-redo` | Undo / Redo in the header above 1200px (tooltip names the change: "Undo: edited ... (⌘Z)"); at 1200px and narrower the same ids are items of the `...` menu (`flow-header-more-menu`). Hidden on a phone |
| `flow-palette-open`, `flow-shortcuts` | `...` menu items "Search and commands" and "Keyboard shortcuts" (not on a phone) |
| `flow-palette` (dialog, `data-state`), `flow-palette-input`, `flow-palette-list`, `flow-palette-no-results` | Cmd/Ctrl+K palette |
| `flow-palette-add` (group), `flow-palette-add-<actionId>` (e.g. `-email`, `-human.approval`) | "Add a step after ..." (behind the selected step, else at the end) |
| `flow-palette-goto` (group), `flow-palette-goto-<nodeId>` | "Go to a step": selects it and opens its panel |
| `flow-palette-actions` (group), `flow-palette-action-<id>` (`save`, `publish`, `run`, `tidy`, `undo`, `redo`, `duplicate`, `copy`, `paste`, `settings`, `runs`, `help`, `shortcuts`) | Editor actions |
| `flow-palette-flows` (group: "Recent flows" with an empty search, "Open a flow" while typing), `flow-palette-flow-<flowId>` | Other flows |
| `flow-live-region` (`role=status`, `aria-live=polite`) | Screen-reader announcements: "Step duplicated", "Undid: ...", "Redid: ...", "2 steps pasted" |
| `shortcuts-dialog`, `shortcuts-group-flow-editor` | The `?` dialog; inside a flow its "Flow editor" group comes first (not listed on a phone) |

Shortcuts (Cmd and Ctrl both work): K palette, S save, Enter run a test (again inside the Run box starts it), Z undo, Shift+Z / Y redo, D duplicate, C copy, V paste (also into another flow, via localStorage `huf.flow.clipboard.v1`), A select every step, Shift+click / Shift+drag select several steps. Text fields keep their own Z / C / V.

## Condition builder (UX-13)
| testid | What |
|---|---|
| `flow-condition-builder` | The rules area of a Condition step (not shown to view-only people, who get `flow-condition-readonly` with the sentence) |
| `flow-condition-match` (`-all`, `-any`) | All of / Any of for the whole check (only with two or more rules or groups); `flow-condition-group-<g>-match` (`-all`, `-any`) for a group |
| `flow-condition-row-<i>` and `flow-condition-group-<g>-row-<i>` | One rule. Parts: `-field` (the data checked; opens the Use data picker), `-op` (the how; options `flow-option-condition-op-<operator>`), `-value` (typed value, or the chip of other data), `-value-picker` ("+ Use data" for a value), `-value-clear` (type a value instead), `-ignore-case`, `-remove`, `-unfinished` (what is missing) |
| `flow-condition-add-rule`, `flow-condition-add-group`, `flow-condition-group-<g>`, `flow-condition-group-<g>-add-rule`, `flow-condition-group-<g>-remove` | Add and remove |
| `flow-condition-sentence` (`flow-condition-sentence-text`, `flow-condition-sentence-empty`) | "Yes when ..." |
| `flow-condition-too-long` | More rules than fit in 500 characters |
| `flow-condition-raw-toggle` | "Write it yourself" / "Back to rules" (remembered in the browser: `huf.flow.condition.writeItYourself`); `flow-condition-raw-locked` replaces it while hand-written text cannot be shown as rules |
| `flow-condition-raw-area`, `flow-field-condition-expression` (text box), `flow-field-condition-expression-picker`, `flow-condition-handwritten` (the "written by hand" note), `flow-hint-condition`, `flow-condition-examples` ("Help and examples"), `flow-condition-raw-too-long` | The text version |
| `flow-branches`, `flow-branch-true` / `flow-branch-false` (`-target`, `-empty`, `-add`) | "Where each path goes": Yes -> step, No -> step, "Add step" asks the canvas for the step picker on that path |

## Step forms in plain words (UX-12, `components/flow/forms/*`)
Every value box is a `DataInput`: its id is `flow-field-<kind>-<field>` (`-picker`, `-preview`, `-preview-text`, `-hint` as for any data box). `<kind>` is the contract type (`agent.run`, `tool.call`, `router.llm`, `foreach`, `human.approval`, `transform`, `state.set`, `doc.create`, `output`).

| testid | What |
|---|---|
| `flow-field-agent.run-agent` (+ `-option-<agent name>`), `flow-field-agent.run-prompt` | Run agent: "Which agent", "What to tell it" (the prompt and its data are one chip box) |
| `flow-field-tool.call-tool_id` | "What to do" for a card that does several things (Sheets, Drive, Slack) and the open-ended Call tool. Not shown for Send email |
| `flow-field-tool.call-input.<field>` | Fields of a tool step (`to`, `subject`, `body`, `channel`, `text`, `spreadsheet_id`, `range`, `url`...) |
| `flow-slack-channel-field` (`data-mode` `pick` / `type`), `flow-slack-channel-picker`, `flow-field-tool.call-input.channel`, `flow-slack-channel-type-it`, `flow-slack-channel-use-list`, `flow-hint-slack-channel` | The one Slack channel control: a list of the workspace's channels, with "Type the channel name instead" and back |
| `flow-field-tool.call-input.method`, `flow-option-http-method-<METHOD>` | HTTP "What to do there" |
| `flow-http-headers`, `flow-json-http-headers-*` (`-toggle`, `-input`, `-format`, `-copy`, `-error`), `flow-http-headers-rows-key-<i>` / `-value-<i>` / `-add` / `-remove-<i>`, `flow-http-headers-example` | Headers as name / value rows, "Edit as JSON" |
| `flow-http-body`, `flow-json-http-body-*`, `flow-http-body-rows-*`, `flow-http-body-example` | "Request body (JSON)" area: fields as rows or JSON, Format, Copy, readable error, "Use an example" |
| `flow-field-router.llm-prompt`, `flow-router-path-<target>`, `flow-router-path-label-<target>`, `flow-router-path-goes-<target>`, `flow-field-router.llm-default`, `flow-more-options` | Choose with AI: the question, each path (name, "then goes to"), the fallback, the model under More options |
| `flow-field-foreach-items`, `flow-field-foreach-collect` (+ `-picker`), `flow-more-options-loop`, `flow-field-foreach-max_iterations`, `flow-field-foreach-on_item_error` | Repeat for each item. The list and the result are pick-only chips (typing does nothing) |
| `flow-field-transform-op`, `flow-option-transform-op-<op>`, `flow-transform-group-<section>`, `flow-hint-transform-example`, `flow-field-transform-input.<param>`, `flow-field-transform-input.<param>-add` / `-item-<i>` / `-remove-<i>` (a short list as rows), `flow-more-options-transform` | Change data |
| `flow-field-state.set-key`, `-value`, `-ttl_seconds` (number) / `-ttl_seconds-unit` / `-unit-<minutes\|hours\|days>`, `flow-more-options-state`, `flow-field-state.get-key`, `flow-field-state.get-default`, `flow-field-state.delete-key` | Save / look up / forget saved data |
| `flow-field-doc.create-doctype` (+ `-option-<name>`), `flow-field-doc.create-fields`, `flow-doc-field-<fieldname>`, `flow-field-doc.create-fields.<i>.name` / `.value` / `.remove`, `flow-field-doc.create-fields.add` | Create document: pick the kind of record, then fields by name |
| `flow-field-human.approval-message`, `-title`, `-approver_type`, `-approver_role` | Wait for approval: question, card headline, who |
| `flow-field-human.approval-approver_users` (group), `-search`, `-list`, `-option-<user>`, `-nobody`, `-chip-<user>`, `-remove-<user>`, `-unknown` | Specific people: picked from people who exist; a saved name nobody has shows in red |
| `flow-approval-card-section`, `flow-field-human.approval-details.<i>.label` / `.value` / `.remove`, `flow-field-human.approval-details.add` | "What the approver sees": up to 6 details |
| `flow-approval-preview`, `-title`, `-note`, `-facts`, `-fact-<i>` | The live card, looks like the bell card |
| `flow-approval-timeout-summary`, `flow-approval-timeout-summary-text`, `flow-approval-timeout-edit` (jumps to the Settings tab field), `flow-branch-timeout` | Setup: what happens if nobody answers, and the "Timed out" path (present only while a time limit is set) |
| `flow-field-human.approval-timeout_ms` (number) / `-timeout_ms-unit` / `-unit-<minutes\|hours\|days>`, `flow-hint-approval-timeout`, `flow-approval-timeout-clear`, `flow-approval-timeout-keep` | Settings tab: "If nobody answers, stop waiting after" in minutes, hours or days; clearing it asks, then removes the Timed out connection |
| `flow-end-outcome`, `flow-field-output-outcome-label`, `flow-end-tone` (radiogroup), `flow-end-tone-<good\|neutral\|bad>`, `flow-end-preview`, `flow-end-preview-chip` (`data-tone`), `flow-end-preview-headline`, `flow-more-options-end`, `flow-field-output-value` | End: the outcome ("Approved", Good / Neutral / Bad) with a preview of the run headline; the result folded under More options |
| `flow-code-editor`, `flow-code-example`, `flow-code-profile`, `flow-code-input-key-<i>` / `-value-<i>` / `-remove-<i>`, `flow-code-inputs-add`, `flow-more-options-code`, `flow-code-timeout` | Execute code: the code, "Start from an example", data for the code, the time limit folded away |
| `flow-run-test-pill` | The grey "Test run" pill beside the status in run details (the history rows keep `flow-run-test-chip-<runId>`, "Test") |
| `flow-run-history-run-test` | Empty run history: the "Run test" button (editors only; closes the history and opens the Run dialog) |
| `flow-node-delete-title`, `flow-node-delete-list` | Delete step dialog: the question ("Delete 3 steps?") and, for several selected steps, the list of their names |
| `flow-use-data-loading` | The "Loading examples" line of the data picker (never shown under "No sample yet") |
| `flow-run-step-note-<stepId>` | Small grey note under a run step ("Stopped at item 2", "Not run for item 2"); a step that did not run in a failed loop has `data-step-status="skipped"` |

## Chat triggers (gateway triggers, `components/flow/forms/GatewayTriggerForm.tsx`, `components/flow/triggers/*`)
One form serves "A chat message" (`gateway`), "A WhatsApp message" (`whatsapp`) and "A Telegram message" (`telegram`); the options come from the server registry, so a new option or channel needs no new ids except `flow-param-<key>`.
| id | What |
|---|---|
| `flow-card-gateway`, `flow-card-whatsapp`, `flow-card-telegram` | Trigger chooser cards |
| `flow-card-connect-<kind>`, `flow-card-connect-link-<kind>` | Under a WhatsApp or Telegram card when none is connected: the note and the link to connect one (`<kind>` = `whatsapp`, `telegram`) |
| `flow-gateway-trigger-<kind>` | The Setup form root (`gateway`, `whatsapp`, `telegram`) |
| `flow-hint-gateway-intro`, `flow-hint-gateway-narrow` | Intro line and the "only start for some messages" line |
| `flow-gateway-chooser`, `flow-gateway-select` | The number / bot / channel picker (a select) |
| `flow-option-gateway-<name>` | One choice in that picker (`<name>` = the stored channel name) |
| `flow-gateway-none`, `flow-gateway-connect` | "No WhatsApp number is connected yet" block and its "Connect a number" / "Connect a bot" link |
| `flow-gateway-loading`, `flow-gateway-load-failed`, `flow-gateway-retry` | Channel list loading, failed, and Try again |
| `flow-gateway-filter-summary` | The one-line summary of what starts the flow (also the canvas card subtitle) |
| `flow-gateway-options` | The options block ("Only start for some messages") |
| `flow-param-<key>` | The control of one option (`keywords`, `starts_with`, `message_kinds`, `chat_scope`, `ignore_bots`, ...). A word list's text box is `flow-param-<key>` too |
| `flow-param-<key>-row`, `flow-param-<key>-help`, `flow-param-<key>-error` | Row, help line and problem message of one option |
| `flow-param-<key>-add` | Add button of a word list (keywords, commands, people) |
| `flow-param-<key>-editor`, `flow-param-<key>-word-<i>`, `flow-param-<key>-remove-<i>` | A word list, its i-th word, and that word's remove button |
| `flow-param-<key>-option-<value>` | One choice of a multiple-choice or select option |
| `flow-gateway-more`, `flow-gateway-more-toggle`, `flow-gateway-more-body` | "More options" folded section: root, toggle, body |
| `flow-gateway-notes` | Read-only facts under the options (STOP words, 24 hour window) |
| `flow-error-trigger.gateway-gateway`, `flow-error-trigger.whatsapp-gateway`, `flow-error-trigger.telegram-gateway` | Required-field message when no channel is chosen |
| `flow-use-data-field-input.<name>` | Data picker rows of a chat trigger, e.g. `input.text` ("Message text"); ids such as `input.sender_id` are never listed |
| `flow-step-test-gateway` (root), `flow-step-test-gateway-last`, `flow-step-test-gateway-sample`, `flow-step-test-gateway-note` | Chat trigger Test tab: root, "Use last real message", "Use a sample message", "Nothing is sent." |
| `flow-step-test-gateway-form`, `flow-step-test-gateway-field-<name>`, `flow-step-test-gateway-use` | The editable sample (one plain field per non-advanced `input.<name>`) and "Use this message" |
| `flow-step-test-gateway-advanced`, `flow-step-test-gateway-advanced-toggle`, `flow-step-test-gateway-advanced-body` | "Advanced" fold of the sample form: internal fields (Event kind, Hours since their last message) |
| `flow-use-data-last-request` | In the data picker: webhooks ("Use last real request") and chat triggers ("Use last real message") |
| `flow-run-started-by` | For a chat run reads "Started by a WhatsApp message from Asha (••••3210) · 5:15 PM" |
