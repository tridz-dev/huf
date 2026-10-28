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
Cards: `flow-card-<id>` with ids
`webhook`, `schedule`, `doc-event` (triggers) and
`agent-run`, `tool-call`, `router`, `condition`, `loop`, `human.approval`, `transform`, `state-get`,
`state-set`, `state-delete`, `doc-create`, `email`, `http-request`, `file`, `slack`, `sheets` (steps).
Card title = node title = sidebar title (derived from `data/actions.ts` / `data/triggers.ts`).

## Canvas nodes
| Test id | Element |
|---|---|
| `flow-node-<nodeId>` | Node wrapper (`data-node-type`, `data-incomplete="true|false"`) |
| `flow-node-title-<nodeId>` | Node title |
| `flow-node-incomplete-<nodeId>` | "Needs setup" marker |
| `flow-node-delete-<nodeId>` | Delete button (on the selected node) |
| `flow-node-delete-dialog`, `flow-node-delete-confirm` | Confirmation for configured nodes |
| `flow-handle-<nodeId>` | Single source handle |
| `flow-handle-in-<nodeId>` | Incoming (target) handle: drop a connection here |
| `flow-handle-<nodeId>-<route>` | Branch handle: `true`, `false`, `approve`, `reject`, `timeout`, `body` |
| `flow-add-step-<nodeId>` | Add-step card after a plain step |
| `flow-add-step-<nodeId>-<route>` | Add-step card for a branch (`true`, `false`, `approve`, `reject`, `body`, `option`, `timeout`) |
| `flow-insert-step-<edgeId>` | "+" on an edge |
| `flow-edge-label-<edgeId>` | Edge label |

## Right sidebar
`flow-config-sidebar`, `flow-sidebar-title`, `flow-config-title`, `flow-sidebar-delete`, `flow-sidebar-close`, `flow-view-only-banner` (view-only users),
`flow-delete-confirm`, `flow-delete-cancel`, `flow-node-title-input`, `flow-node-incomplete` (summary banner),
`flow-trigger-type`, `flow-trigger-change`, `flow-edge-config`, `flow-edge-meaning`, `flow-edge-label`,
`flow-branches`, `flow-branch-<route>`, `flow-branch-<route>-empty`.

## Fields: `flow-field-<type>-<field>`, errors: `flow-error-<type>-<field>`
Dropdown options inside Selects: `flow-option-<name>`; Combobox options: `<field testid>-option-<value>`.

| Type | Fields |
|---|---|
| `trigger.webhook` | `url` (read-only), `secret`, `method` (options `flow-option-webhook-method-GET|POST`) |
| | buttons `flow-webhook-copy-url`, `flow-webhook-copy-secret`, `flow-webhook-regenerate`; usage blocks `flow-webhook-usage`, `-header`, `-curl` (no query-string form: the secret is header-only) |
| `trigger.schedule` | `frequency` (options `flow-option-schedule-frequency-<minutes|hours|daily|weekly|monthly|custom>`), `every`, `minute`, `hour`, `weekday`, `monthday`, `cron`; preview `flow-schedule-preview` |
| `trigger.doc-event` | `doctype`, `event` (options `flow-option-doc-event-<event>`) |
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
| `flow-node-tool-<nodeId>` | Human tool name on a tool step |
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
| `flow-edge-remove-<edgeId>` | "Remove connection" button on the selected line |
| `flow-edge-delete-dialog`, `flow-edge-delete-confirm` | Confirmation shown by that button and by the Delete key on a selected line |
| `flow-edge-config` | Sidebar "Connection" panel of the selected line |
| `flow-node-orphan-<nodeId>` | "Nothing leads to this step" on a step no trigger reaches |
| `flow-delete-mode`, `flow-delete-mode-reconnect`, `flow-delete-mode-cascade` | Choice in the step delete dialog (`flow-node-delete-dialog`) when the step has a step after it: "Remove step and reconnect" (default) / "Remove step and everything after it" |
| `flow-published-badge`, `flow-unpublish`, `flow-unpublish-dialog`, `flow-unpublish-confirm` | Published state in the header; Unpublish replaces Publish while the flow is published |
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
| `integration-test-connection` | "Test connection" button (read-only check; typed values are used when filled in, otherwise the saved ones) |
| `integration-test-result` (`data-status` = Connected / Rejected / Not connected) | Result line with the plain reason |
| `flow-step-<kind>-input.<field>-hint` | One-line "where do I find this" under a tool input (Slack channel, Sheets and Drive IDs) |

## Slack channels and run summaries (wp16)
| Test id | Element |
|---|---|
| `flow-run-step-summary-<nodeId>` | One-line plain summary above a finished integration step's output (Posted to, Sent to, status from host, row/file counts) |
| `flow-run-step-raw-<nodeId>` | Collapsed "Show raw response" (`<details>`); the secrets-stripped output stays at `flow-run-step-output-<nodeId>` inside it |
| `slack-load-channels`, `slack-channels`, `slack-channel-list`, `slack-channel-<name>`, `slack-copy-id-<name>`, `slack-channels-error`, `slack-channels-empty` | Integration > Recipients tab (saved Slack integration): read-only "Load channels" list with copy-ID buttons |
| `flow-slack-channel-picker`, `flow-field-slack-channel-pick`, `flow-slack-channel-picker-error` | "Or pick a channel" searchable list under the Slack step's Channel field (only when Slack is connected) |
