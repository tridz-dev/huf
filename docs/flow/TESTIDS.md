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
| `flow-validation-summary` | "N things to finish" link (only while something is incomplete) |
| `flow-add-trigger` | Add trigger button (when the flow has no trigger) |
| `flow-rail-trigger`, `flow-rail-agent`, `flow-rail-condition`, `flow-rail-tool`, `flow-rail-data` | Left palette rail |

## Palette modal
`flow-trigger-modal`, `flow-action-modal`, `flow-modal-add-trigger`, `flow-modal-cancel`.
Trigger modal: one list of cards (no tab bar, no search); the chosen card has `data-selected="true"` and a check `flow-card-check-<id>`; hint line `flow-trigger-hint` always takes its space. Empty trigger: card button `flow-node-choose-trigger-<nodeId>` and side-panel button `flow-trigger-choose` (panel `flow-trigger-unset`) both open `flow-trigger-modal`.
Cards: `flow-card-<id>` with ids
`webhook`, `schedule`, `doc-event` (triggers) and
`agent-run`, `tool-call`, `router`, `condition`, `loop`, `human.approval`, `transform`, `state-get`,
`state-set`, `state-delete`, `doc-create`, `email`, `http-request`, `file`, `slack`, `sheets` (steps), and `code-run` (Execute code: only offered when the server allows code in Flows and the user holds `flows.execute_code`, see wp19 below).
Card title = node title = sidebar title (derived from `data/actions.ts` / `data/triggers.ts`).

## Canvas nodes
| Test id | Element |
|---|---|
| `flow-node-<nodeId>` | Node wrapper (`data-node-type`, `data-incomplete="true|false"`) |
| `flow-node-title-<nodeId>` | Node title |
| `flow-node-subtitle-<nodeId>` | One line saying what the step does ("Send a message to #alerts"); full text in the tooltip |
| `flow-node-status-<nodeId>` | The card's ONE status word (`data-status`: ready, needs-setup, not-connected, orphan, running, waiting, done, failed). Never wraps; cards are the same size in every state |
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
| `flow-edge-label-<edgeId>` | Branch name pill on a connection (Yes/No, Approved/Rejected/Timed out, For each item/When done, a router path in full, Next item on the loop-back line); 12px on screen at any zoom |

## Right sidebar
`flow-config-sidebar`, `flow-sidebar-title`, `flow-config-title`, `flow-sidebar-delete`, `flow-sidebar-close`, `flow-view-only-banner` (view-only users),
`flow-delete-confirm`, `flow-delete-cancel`, `flow-node-title-input`, `flow-node-incomplete` (summary banner),
`flow-trigger-type`, `flow-trigger-change`, `flow-edge-config`, `flow-edge-meaning`, `flow-edge-label`,
`flow-branches`, `flow-branch-<route>`, `flow-branch-<route>-empty`.

## Fields: `flow-field-<type>-<field>`, errors: `flow-error-<type>-<field>`
Dropdown options inside Selects: `flow-option-<name>`; Combobox options: `<field testid>-option-<value>`.

| Type | Fields |
|---|---|
| `trigger.webhook` | `url` (read-only address), `secret` (read-only, masked `****c3e6` until Show; `data-masked`), `method` (options `flow-option-webhook-method-GET|POST`) |
| | buttons `flow-webhook-copy-url`, `flow-webhook-copy-secret`, `flow-webhook-secret-toggle` (Show for 30 s / Hide), `flow-webhook-regenerate` (opens `flow-webhook-regenerate-dialog` with `-cancel` / `-confirm`); note `flow-webhook-secret-new-note`; pill `flow-webhook-live`; panel `flow-webhook-panel` |
| | data it sends: `flow-webhook-data`, `flow-webhook-fields` / `flow-webhook-field` (plain rows), buttons `flow-webhook-paste-sample`, `flow-webhook-use-last`, `flow-webhook-clear-sample`, JSON area `flow-json-webhook-sample` (`-input`, `-help`, `-copy`, `-format`, `-error`), `flow-webhook-sample-save` / `-cancel`, `flow-webhook-sample-note` |
| | developer reference (closed until opened): `flow-webhook-usage` (`data-open`), `flow-webhook-howto-toggle`, `flow-webhook-howto`, JSON area `flow-json-webhook-body` (title "Request body (JSON)"), command `flow-webhook-usage-curl` with `flow-webhook-usage-curl-copy`, `flow-webhook-usage-secret-note`, `flow-webhook-responses` |
| `trigger.schedule` | `frequency` (options `flow-option-schedule-frequency-<minutes|hours|daily|weekly|monthly|custom>`), `every` (options `flow-option-schedule-every-<n>`), `minute` (hours only), `time` (daily, weekly, monthly), `weekday` (group) with `weekday-<0..6>` buttons and presets `flow-schedule-preset-<weekdays|weekend|everyday>`, `monthday` (options `flow-option-schedule-monthday-<1..31|last>`), `zone` (time zone; options `flow-field-trigger.schedule-zone-option-<IANA name>`), `cron` (only under Custom); `flow-schedule-preview` wraps `flow-schedule-summary` (sentence), `flow-schedule-timezone` (how the time shows in the browser) and `flow-schedule-next-runs` / `flow-schedule-next-run` |
| `trigger.doc-event` | `doctype` (searchable list, `-search`, options `flow-field-trigger.doc-event-doctype-option-<name>`), `event` (options `flow-option-doc-event-<event>`); sentence `flow-data-sentence`, panel `flow-data-trigger`, `flow-doc-event-filter` (the "Only when... coming soon" note) |
| trigger panel | `flow-trigger-apply`, `flow-trigger-clear`, `flow-trigger-disabled-reason` |
| `agent.run` | `agent`, `prompt`, `prompt_bindings`; `flow-binding-<name>`; picker `flow-agent-run-variable-picker` (+ `-item-<ref>`) |
| `tool.call` | `tool_id`, `input.<key>` (e.g. `input.to`, `input.subject`, `input.body`, `input.channel`, `input.text`, `input.url`, `input.method`, `input.headers`, `input.body`); every value control has a `-mode` select (`flow-field-tool.call-input.to-mode`) |
| `router.llm` | `prompt`, `options` (list), `flow-router-path-label-<targetNodeId>`, `flow-router-path-<targetNodeId>`, `flow-router-no-paths`, `default` |
| `condition` | `expression`; branches `flow-branch-true`, `flow-branch-false` |
| `foreach` | `items`, `max_iterations`, `on_item_error` (`flow-option-loop-on-error-fail|skip`), `collect`; branches `flow-branch-body`, `flow-branch-next`; pickers `flow-loop-items-picker`, `flow-loop-collect-picker` |
| `human.approval` | `message`, `approver_type` (required; `flow-option-approver-role|user`; inline error `flow-error-actionConfig-approver_type`), `approver_role`, `approver_users`, `timeout_ms` (minutes in the UI); branches `flow-branch-approve|reject|timeout` |
| `transform` | `op` (`flow-option-transform-op-<op>`), `input.<param>` |
| `state.get|set|delete` | `key`, `default`, `value`, `ttl_seconds` |
| `doc.create` | `doctype`, `fields.<i>.name`, `fields.<i>.value`, `fields.add` |
| `output` | `flow-field-output-value` |

Validation messages: `flow-error-<type>-<field>` (role="alert"), plus the node-level banner `flow-node-incomplete`.
Blocked saves surface a toast; the first offending node is selected.

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
| `flow-run-dialog`, `flow-run-payload`, `flow-run-payload-error`, `flow-run-start`, `flow-run-cancel` | Run dialog (JSON input data) opened by the Run button and the list card Run action |
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
| `flow-code-input-key-<i>`, `flow-code-input-value-<i>` | Name and value of input row `i` (value is a Flow value control: `-mode` and `-picker` suffixes as for other fields); remove with `flow-code-input-remove-<i>` |
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
| `flow-minimap` | Overview map, bottom-left of the canvas (hidden under 8 steps and when the canvas is narrower than 640px) |
| `flow-palette-intro` | One-sentence intro under the "Choose what starts this flow" / "Add a step" title |
| `flow-palette-empty` | Empty state of the palette search ("No steps match ..."), with `flow-palette-clear-search` ("Show all") |
| `flow-palette-section-<category>` | A labelled palette section: agent (AI), control (Decide and repeat), people, data (Work with data), apps, advanced |
| `flow-transform-group-<section>` | Labelled group in the Transform operation list: change-text, find-in-text, pick-rows, group-combine, values |
| `flow-card-desc-<cardId>` | The one-line "what does this step do" under a palette card |
| `flow-config-hint` | Intro sentence at the top of a step or trigger form |
| `flow-hint-<form>-<field>` | One-line hint under a field (for example `flow-hint-webhook-secret`, `flow-hint-loop-max`, `flow-hint-approval-timeout`, `flow-hint-transform-op`, `flow-hint-transform-example`, `flow-hint-condition`) |
| `<field testid>-hint` | Hint under a value input (URL, Subject, Spreadsheet ID ...); `<field testid>-mode-help` explains Reference / Template / JSON |
| `flow-condition-examples`, `flow-schedule-examples`, `flow-doc-event-explained` | Folded example lists (condition syntax, cron examples, what each Data event means) |
| `flow-webhook-responses` | What 200 / 403 / 405 / 429 mean (inside the closed-by-default developer reference) |
| `flow-hint-schedule-intro`, `flow-hint-schedule-every`, `flow-hint-schedule-monthday`, `flow-hint-schedule-zone`, `flow-hint-schedule-cron` | Schedule intro and field help |
| `flow-hint-doc-event-intro`, `flow-hint-doc-event-doctype`, `flow-hint-doc-event-event` | Data trigger help |
| `flow-hint-step-name`, `flow-hint-trigger-type`, `flow-hint-step-result`, `flow-sidebar-empty-hint` | Sidebar help lines |
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
| `flow-run-title` (`data-run-id`) | Run details header: "Run #N · started by you · 2 mins ago" (never the internal id) |
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
| `flow-list-filters`, `flow-list-search`, `flow-list-status-filter`, `flow-list-category-filter`, `flow-list-sort`, `flow-list-limit-note`, `flow-list-error` | List filter row ("All statuses", "All categories", "Recently updated"), the "Showing N of M" note with Show more, load error |
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
| `flow-phone-banner`, `flow-phone-view-steps`, `flow-phone-show-map` | Phone: the "Editing steps works best on a larger screen" note with View steps, and the Show map button |
| `flow-steps-list`, `flow-step-card-<nodeId>` (+ `-title-`, `-summary-`, `-status-`), `flow-step-branch-<nodeId>` | Phone steps list: one card per step in reading order (icon, title, one line, status); branch name above the first step of a branch |
| `flow-run-decision-bar`, `flow-run-decision-inline`, `flow-run-cannot-decide`, `flow-run-back` | Run details: sticky Approve / Reject bar on a phone, the inline pair elsewhere, the sentence shown to someone who may not decide, the "Runs" back button |
| `flow-approval-group-<firstRunId>`, `flow-approval-group-heading` | Bell: identical requests grouped under "3 waiting: Order approval" (every request keeps its own `flow-approve-<runId>` / `flow-reject-<runId>`) |
| `no-access-page`, `no-access-title`, `no-access-body`, `no-access-go-flows`, `no-access-go-hub` | "You don't have access to this page" (Hub, Flows, Executions, Settings, Agents, Dashboard) |
