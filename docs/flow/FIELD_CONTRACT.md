# Flow Definition field contract (graph IR, profile `flow`)

Status: authoritative for the Flow builder UI, the Flow engine and the save-time validator.
Source of truth: `huf/ai/graph/graph_ir.schema.json` (`$defs/FlowGraph`), enforced on every save by
`FlowDefinition._validate_definition_json` -> `huf.ai.graph.validator.validate_flow_graph`.
Pre-release: there are no aliases and no legacy shapes. A UI or engine that reads or writes any name
not listed here is wrong; fix the UI/engine, not the schema. Tests: `huf/ai/graph/tests/test_flow_field_contract.py`
validates every example in this file (the canonical flow below is extracted from this document and run).

## 1. Document envelope

| Field | Type | Required | Notes |
|---|---|---|---|
| `schema_version` | string, const `"1.0.0"` | yes | not an integer |
| `profile` | string, const `"flow"` | yes | informational; validation is by profile argument |
| `fingerprint` | string, `^[a-f0-9]{64}$` | yes | sha256 hex of canonical form |
| `entry` | node id, or non-empty array of node ids | yes | array when starting from triggers (one id per trigger) |
| `nodes` | array of node, min 1 | yes | flat list; **no `edges` array exists** |
| `contract` | object | yes | see section 4 |

No other top-level keys (`edges`, `settings`, `viewport`, ... are rejected).

Every node: `{ "id", "type", "config", "next"?, "on_error"? }`.

* `id`: `^[a-zA-Z_][a-zA-Z0-9_]*$`, max 64, unique. Ids with `-` or `.` are rejected.
* `type`: exact string from section 2.
* `config`: object; every config object below is `additionalProperties: false` (unknown keys rejected).
* `next`: default successor id, or absent. Never write `"next": null` on `output`; `condition`, `router.*`, `human.approval` and `output` must NOT carry `next` at all.
* `on_error`: node id to route to when the node raises; absent means the run fails.
* Positions / canvas metadata / labels are NOT part of the definition (UI keeps them elsewhere); UI-only keys inside `config` are rejected.

An edge is not a first-class object: it is the pointer fields `next`, `on_error`, and the per-type routing
fields in section 3. The UI must derive canvas edges from these and write them back; edge-level
`outcome` / `priority` / `condition` / `label` do not exist (the routing field *is* the outcome).

## 2. Node and trigger types

`Value` (used by `input` objects etc.) is one of: literal (string/number/bool/null); reference
`{"$from": "<path>"}`; template `{"$template": "Hi {name}", "vars": {"name": <Value>}}`; array of Values;
object of Values (an object may not itself contain a `$from` key). Reference path grammar:
`^(input|trigger|row|foreach\.(item|index)|<node_id>)(\.<ident>|\[<n>\])*$`, and a referenced node must be a
proven predecessor on every path. `Expression` is a restricted Python subset, 1-500 chars, subscripts not
attributes: `input['amount'] > 100`, not `input.amount` and not `context["x"]`.

### Triggers

| UI item | `type` | config field | JSON type | Required | Constraint |
|---|---|---|---|---|---|
| Webhook | `trigger.webhook` | `method` | string | yes | enum `GET`, `POST` |
| | | `secret` | string | yes | length 8-256; receiver compares the presented key to this value (constant time), fail closed |
| Schedule | `trigger.schedule` | `cron` | string | yes | min length 1; 5-part cron (`minute hour day month dow`), evaluated in server system time |
| Data (doc event) | `trigger.doc-event` | `doctype` | string | yes | min length 1, literal |
| | | `event` | string | yes | enum `after_insert`, `on_update`, `on_submit`, `on_cancel`, `on_trash` |
| (placeholder, not runnable) | `trigger.unset` | none | | | empty config; cannot activate |

Notes:
* `auth`, `apiKey`, `webhook_key`, `intervalType`, `interval`, `cronExpression`, `schedule_name`, `timezone`, `filters`, `PUT`, `DELETE`, `on_delete` are all invalid. The UI compiles any "every N hours/days" picker to a cron string before saving. `timezone` is not offered: the scheduler (`set_flow_trigger`) runs cron in system time, so there is nothing to consume it.
* Webhook method: the receiver (`flow_webhook` / `flow_webhook_clean`) does not branch on the method; the schema restricts to GET/POST so the UI never promises PUT/DELETE.
* Doc-event filters/conditions are not part of the node (they live on the Automation Trigger created by `set_flow_trigger`).
* A trigger node has `next` like any node; multiple triggers each point into the same flow body.

### Actions

| UI action | `type` | config fields (all keys; `*` required) |
|---|---|---|
| Run Agent | `agent.run` | `agent`* string (Agent name), `prompt`* string (placeholders `{name}`), `prompt_bindings` object name -> Value |
| Call Tool | `tool.call` | `tool_id`* string (literal, `^[a-zA-Z_][a-zA-Z0-9_.]*$`, never a reference), `input`* object of Value, `timeout_ms` int >=1, `approved` bool. (`recovery` was removed: flows have no recovery modes.) |
| LLM Router | `router.llm` | `prompt`* string, `options`* array (min 1) of `{label* string, node_id* id}`, `default`* id, `model` string (optional; name of an AI Model record, absent = first keyed provider's default chat model). No `next`. |
| (deterministic router) | `router.decision` | `policy`* string, `options`*, `default`* (same shapes). No `next`. Not offered by the UI. |
| Condition | `condition` | `expression`* Expression, `on_true`* id, `on_false`* id. No `next`. |
| Loop | `foreach` | `items`* Reference (`{"$from": ...}` only), `body`* array (min 1) of ids, `max_iterations`* int >=0, `on_item_error`* enum `fail`/`skip`, `collect`* Reference, `item_var` ident (default `item`), `index_var` ident (default `index`). Done edge is the node's `next`. |
| Human in Loop | `human.approval` | `message`* string, `approve_next`* id, `reject_next`* id, `timeout_next` id, `timeout_ms` int >=1, `approver_type`* enum `role`/`user`, `approver_role` string (required when `role`), `approver_users` array of string (min 1, required when `user`). No `next`. |
| Transform Data | `transform` | `op`* enum (below), `input`* object of Value |
| Execute Code | `tool.call` | `tool_id` `run_python`, `input` `{code: ...}`. **Unresolved, see section 6.** |
| Send Email | `tool.call` | `tool_id` `gmail_send_email`; `input` `{to*, subject*, body*}` |
| HTTP Request | `tool.call` | `tool_id` `http_request`; `input` e.g. `{url*, method, headers, body}`. **Tool not registered, see section 6.** |
| File Operations | `tool.call` | `tool_id` one of `gdrive_list_files` (`limit`, `query`), `gdrive_search_files` (`query`*), `gdrive_get_file` (`file_id`*) |
| Slack | `tool.call` | `tool_id` `slack_send_message`; `input` `{channel*, text*}` (also `slack_send_thread_reply` with `thread_ts`*) |
| Google Sheets | `tool.call` | `tool_id` `gsheets_read` (`spreadsheet_id`*, `range`), `gsheets_update` (`spreadsheet_id`*, `range`*, `data`*), `gsheets_create` (`title`*) |
| End | `output` | `value`* Value. No `next` key at all (not even null). |
| Get / Set / Delete state | `state.get` / `state.set` / `state.delete` | get: `key`* Value, `default` Value; set: `key`*, `value`*, `ttl_seconds` int 1-2592000 or Value; delete: `key`* |
| Create document | `doc.create` | `doctype`* string literal (must be in site allow-list `huf_flow_create_doc_doctypes`), `fields`* object of Value |
| (assertions) | `validate` | `assertions`* array (min 1) of `{expression*, code*, message*}` |

`tool.call` UI presets (Email, Slack, Sheets, File, HTTP, Code) are `tool.call` and carry ONLY
`tool_id`/`input` (+ optional `timeout_ms`, `approved`). The legacy `tool_name`, `args`,
`parameters`, `output.save_result_to_context`, `mcp_server`, `agent_name`, `gateway` keys are rejected by the schema.
Results are read by later nodes as `{"$from": "<node_id>"}` (or `<node_id>.field`); there is no
"save result to context key".

`transform.op` enum (from `huf.ai.graph.transforms.REGISTRY`): `select`, `filter`, `sort`, `limit`, `group_by`,
`aggregate`, `join`, `lookup`, `batch`, `distinct`, `coalesce`, `lower`, `upper`, `trim`, `replace`, `contains`,
`starts_with`, `split_first`, `regex_extract`, `concat`. Input keys per op: select(`rows`,`fields`),
filter(`rows`,`where`), sort(`rows`,`key`,`order`), limit(`rows`,`count`), group_by(`rows`,`key`),
aggregate(`rows`,`field`,`op`), join(`left`,`right`,`left_key`,`right_key`,`how`), lookup(`rows`,`from`,`key`,`on`,`as`),
batch(`rows`,`size`), distinct(`rows`,`key`), coalesce(`values`), concat(`parts`), regex_extract(`text`,`pattern`,`group`,`default`),
text ops take `text`. The old UI modes map as: **Copy** = a `{"$from": ...}` reference used directly in a later node's input (no node needed;
or `coalesce`), **Map** = `select`, **Template** = a `{"$template", "vars"}` Value (or `concat`). The legacy
`transformations: [{source_field, target_field, operation}]` shape does not exist.

## 3. Edge semantics (routing fields)

| Node | Routing fields | Semantics |
|---|---|---|
| any non-routing node | `next` (optional), `on_error` (optional) | `next` absent = terminal for its chain. `on_error` runs instead of failing the run. |
| `condition` | `config.on_true`, `config.on_false` | both required, both must exist; True branch -> `on_true`, False -> `on_false`. Node has no `next`. UI "True"/"False" handles write these; they must not be the same node unless intended. |
| `router.llm` / `router.decision` | `config.options[i].node_id`, `config.default` | model picks an option by `label`; no match or failure goes to `default` (required, so routing is total). Node has no `next`. |
| `foreach` (Loop) | `config.body` (ids), `next` | `body` lists top-level node ids run once per item, in chain order via their own `next`; the last body node has no `next` (no return edge to the loop; a back-edge is a cycle and is rejected). Body nodes must not be reachable by any other path. `next` is the "done" edge, taken after the last item. Per-item values: `{"$from": "foreach.item"}`, `{"$from": "foreach.index"}`. `collect` is a reference evaluated per item (typically a body node, `{"$from": "<body_node>"}`) producing the node's output list. `max_iterations` is capped by `contract.limits.max_foreach_iterations`. |
| `human.approval` | `config.approve_next`, `config.reject_next`, `config.timeout_next` | approve -> `approve_next`; reject -> `reject_next`; no decision within `timeout_ms` -> `timeout_next` (if absent, the run times out/fails). No `next`. Approver restriction: `approver_type: "role"` requires `approver_role` and forbids `approver_users`; `"user"` requires `approver_users` and forbids `approver_role`; `approver_type` is REQUIRED: a flow without it fails at save with a readable message. The decision record is read downstream as `{"$from": "<approval_node_id>"}`. |
| `output` | none | terminal; no `next`. |

Validator also checks: all targets exist, every node reachable from `entry`, no cycles, all references resolve to
proven ancestors, expressions parse, `transform.op` known, `contract.limits` within policy ceilings, declared
`permission_envelope` covers the tools actually called.

## 4. `contract`

| Field | Type | Required | Notes |
|---|---|---|---|
| `input_schema` | JSON Schema object | yes | `{}` ok |
| `output_schema` | JSON Schema object | yes | `{}` ok |
| `applies_when` | array of Expression | yes | may be empty |
| `permission_envelope` | `{read, write, http, code}` | yes | `read`/`write`: arrays of `{doctype, ...}`; `http`/`code`: `"none"` or non-empty array of **tool ids** the graph invokes that carry that surface (e.g. `["http_request"]`, `["run_python"]`). Must cover whatever the graph calls. |
| `limits` | object | yes | all 9 keys required (`max_nodes`, `max_rows`, `max_output_bytes`, `max_parallel_calls`, `max_foreach_iterations`, `max_external_calls`, `max_writes`, `max_wall_time_ms`, `fail_closed: true`), within `POLICY_LIMIT_CEILINGS` |

## 5. Canonical example (contains every UI trigger and action type)

```json
{
  "schema_version": "1.0.0",
  "profile": "flow",
  "fingerprint": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "entry": [
    "t_webhook",
    "t_schedule",
    "t_doc"
  ],
  "nodes": [
    {
      "id": "t_webhook",
      "type": "trigger.webhook",
      "config": {
        "method": "POST",
        "secret": "change-me-webhook-secret"
      },
      "next": "n_prep"
    },
    {
      "id": "t_schedule",
      "type": "trigger.schedule",
      "config": {
        "cron": "*/15 * * * *"
      },
      "next": "n_prep"
    },
    {
      "id": "t_doc",
      "type": "trigger.doc-event",
      "config": {
        "doctype": "ToDo",
        "event": "after_insert"
      },
      "next": "n_prep"
    },
    {
      "id": "n_prep",
      "type": "transform",
      "config": {
        "op": "trim",
        "input": {
          "text": {
            "$from": "input.message"
          }
        }
      },
      "next": "n_agent"
    },
    {
      "id": "n_agent",
      "type": "agent.run",
      "config": {
        "agent": "support-triage",
        "prompt": "Classify this request: {message}",
        "prompt_bindings": {
          "message": {
            "$from": "n_prep"
          }
        }
      },
      "next": "n_cond"
    },
    {
      "id": "n_cond",
      "type": "condition",
      "config": {
        "expression": "input['amount'] > 100",
        "on_true": "n_router",
        "on_false": "n_done_small"
      }
    },
    {
      "id": "n_router",
      "type": "router.llm",
      "config": {
        "prompt": "Is this urgent or routine?",
        "options": [
          {
            "label": "urgent",
            "node_id": "n_human"
          },
          {
            "label": "routine",
            "node_id": "n_loop"
          }
        ],
        "default": "n_loop"
      }
    },
    {
      "id": "n_human",
      "type": "human.approval",
      "config": {
        "message": "Approve escalation?",
        "approver_type": "role",
        "approver_role": "System Manager",
        "approve_next": "n_loop",
        "reject_next": "n_done_rejected",
        "timeout_next": "n_done_rejected",
        "timeout_ms": 86400000
      }
    },
    {
      "id": "n_loop",
      "type": "foreach",
      "config": {
        "items": {
          "$from": "input.recipients"
        },
        "item_var": "item",
        "index_var": "index",
        "body": [
          "n_email"
        ],
        "max_iterations": 100,
        "on_item_error": "skip",
        "collect": {
          "$from": "n_email"
        }
      },
      "next": "n_http"
    },
    {
      "id": "n_email",
      "type": "tool.call",
      "config": {
        "tool_id": "gmail_send_email",
        "input": {
          "to": {
            "$from": "foreach.item"
          },
          "subject": "Update",
          "body": {
            "$template": "Hello {who}",
            "vars": {
              "who": {
                "$from": "foreach.item"
              }
            }
          }
        }
      }
    },
    {
      "id": "n_http",
      "type": "tool.call",
      "config": {
        "tool_id": "http_request",
        "input": {
          "url": "https://api.example.com/notify",
          "method": "POST",
          "body": {
            "ok": true
          }
        },
        "timeout_ms": 30000
      },
      "next": "n_slack"
    },
    {
      "id": "n_slack",
      "type": "tool.call",
      "config": {
        "tool_id": "slack_send_message",
        "input": {
          "channel": "#ops",
          "text": "Flow finished"
        }
      },
      "next": "n_sheets"
    },
    {
      "id": "n_sheets",
      "type": "tool.call",
      "config": {
        "tool_id": "gsheets_read",
        "input": {
          "spreadsheet_id": "1AbC",
          "range": "Sheet1!A1:D10"
        }
      },
      "next": "n_file"
    },
    {
      "id": "n_file",
      "type": "tool.call",
      "config": {
        "tool_id": "gdrive_list_files",
        "input": {
          "limit": 20
        }
      },
      "next": "n_code"
    },
    {
      "id": "n_code",
      "type": "tool.call",
      "config": {
        "tool_id": "run_python",
        "input": {
          "code": "print(1)"
        }
      },
      "next": "n_state_set"
    },
    {
      "id": "n_state_set",
      "type": "state.set",
      "config": {
        "key": "last_run",
        "value": true,
        "ttl_seconds": 3600
      },
      "next": "n_state_get"
    },
    {
      "id": "n_state_get",
      "type": "state.get",
      "config": {
        "key": "last_run",
        "default": false
      },
      "next": "n_doc"
    },
    {
      "id": "n_doc",
      "type": "doc.create",
      "config": {
        "doctype": "ToDo",
        "fields": {
          "description": "Flow done"
        }
      },
      "next": "n_validate"
    },
    {
      "id": "n_validate",
      "type": "validate",
      "config": {
        "assertions": [
          {
            "expression": "input['amount'] >= 0",
            "code": "NEG",
            "message": "amount must be non-negative"
          }
        ]
      },
      "next": "n_done"
    },
    {
      "id": "n_done",
      "type": "output",
      "config": {
        "value": {
          "$from": "n_doc"
        }
      }
    },
    {
      "id": "n_done_small",
      "type": "output",
      "config": {
        "value": "skipped"
      }
    },
    {
      "id": "n_done_rejected",
      "type": "output",
      "config": {
        "value": "rejected"
      }
    }
  ],
  "contract": {
    "input_schema": {
      "type": "object"
    },
    "output_schema": {},
    "applies_when": [],
    "permission_envelope": {
      "read": [],
      "write": [
        {
          "doctype": "ToDo"
        }
      ],
      "http": [
        "http_request"
      ],
      "code": [
        "run_python"
      ]
    },
    "limits": {
      "max_nodes": 50,
      "max_rows": 10000,
      "max_output_bytes": 1000000,
      "max_parallel_calls": 4,
      "max_foreach_iterations": 200,
      "max_external_calls": 100,
      "max_writes": 10,
      "max_wall_time_ms": 60000,
      "fail_closed": true
    }
  }
}
```

Legend: `t_*` triggers; `n_prep` Transform Data; `n_agent` Run Agent; `n_cond` Condition; `n_router` LLM Router;
`n_human` Human in Loop; `n_loop` Loop (body `n_email`; done edge = `next: n_http`); `n_email` Send Email; `n_http` HTTP Request;
`n_slack` Slack; `n_sheets` Google Sheets; `n_file` File Operations; `n_code` Execute Code; `n_done*` End.
The `n_state_*`, `n_doc`, `n_validate` nodes are non-UI extras kept so the example covers all Flow node types
except `router.decision`, `trigger.unset` (covered in the unit test).
The example is valid with a classifier that marks `http_request` as an http tool and `run_python` as a code tool.

## 6. Open items needing a decision (not resolvable in the schema)

1. **Execute Code**: `run_python` is registered by `huf/install.py` (type "Code Execution") but Flow runs have no Agent Execution
   Profile, so the runtime registry refuses it on every call and `list_flow_tools` deliberately hides it. The schema-correct mapping is
   `tool.call` + `tool_id: "run_python"`, but it cannot work in a Flow today. Either hide the card, or give Flows an execution profile.
2. **HTTP Request**: resolved. Built-in tool `http_request` (App Provided, declared in `huf/ai/tools/_registry.py` `HTTP_TOOLS`, function `huf.ai.http_handler.http_request(url, method="GET", headers=None, body=None)`) matches the `input` contract `{url, method, headers, body}`. Returns a JSON string with `success` (true only for 2xx), `status_code`, `headers` subset, `body` (64KB cap), `truncated`.
3. **Gateway / MCP binding**: the engine reads `config.mcp_server` and `config.gateway` on `tool.call`; the schema forbids them. The engine
   must resolve MCP tools by unique tool id (`find_unique_mcp_server_for_tool`). `FlowDefinition._validate_gateway_authority` is therefore dead for saved flows.
4. **Backend consumers of the old names**: resolved. `flow_webhook` authenticates with the trigger node's `secret` (`X-Huf-Secret` or `?secret=`), the engine reads only the contract names (`on_true`/`on_false`, `foreach` body fields, `tool_id`/`input`, `approver_*`), `get_pending_approvals` and the approve/reject endpoints read the `waiting` keys in section 7, and `huf/ai/gateways/approvals.py` reads `approver_type`. Legacy keys (`auth`, `apiKey`, `webhook_key`, `approval_type`, `title`, `instructions`, `true_node`, `iterate_over`, `tool_name`) are ignored.
5. `approver_type` is required by the schema (pre-release: no legacy approval nodes). `parallel` and `tool.call.recovery` are Flow-removed; they remain only in the Procedure profile.

## 7. Engine behaviour notes (verified against `huf/ai/flow/engine.py`)

**Templating and expressions**
* `{{var}}` is NOT supported anywhere. In `agent.run.prompt`, `{name}` placeholders are filled from `prompt_bindings`; `{{`/`}}` are literal braces. Other dynamic values use `{"$from": ...}` or `{"$template": "...", "vars": {...}}`.
* `router.llm.prompt` and `human.approval.message` are plain text: no placeholders are substituted.
* `condition` expressions use `input[...]` roots (AST-restricted evaluator).

**Approvals**
* The `waiting` JSON of a paused run holds: `type` (`approval`), `node_id`, `message`, `approver_type` (`role`|`user`), `approver_role`, `approver_users`, `timeout_next`, `timeout_ms`, `timeout_at` (ISO). `get_pending_approvals` returns these (plus `title`/`instructions`/`approval_type` aliases for the current frontend).
* Fail closed, same rule for approve and reject (`engine.check_approver` / `verify_approval_permission`): `role` needs the role, `user` needs membership in `approver_users`, anything else (absent type, empty role/list) means System Manager only. A System Manager can always decide. `get_pending_approvals` lists only runs the caller may decide.
* Timeouts: `timeout_ms` sets `timeout_at` when the run pauses. The every-minute scheduler job `huf.ai.flow.triggers.expire_due_approvals` calls `engine.expire_approval`, which routes to `timeout_next` (decision `timeout`) or fails the run when none is set. Resolution is one minute at best, and a run whose deadline passed while the scheduler was down expires on the next tick.

**Routing and models**
* `router.llm` makes one direct completion with the optional `model` (AI Model name), else the first keyed AI Provider's default chat model (no agent involved). An unmatched reply, no keyed provider, or any LLM failure routes to the node's required `default` (reason `no_match` / `llm_failed: ...`).

**Limitations**
* Recovery: there is no flow-run recovery sweeper; a worker crash mid-node leaves the run `Running` until it is failed or re-run by hand (only approval expiry is scheduled).
* `timeout_ms` on `tool.call` bounds the wait for the result but cannot cancel an already-running tool.
* Run settings: only `mode`, `max_hops`, `conversation_mode`, `max_foreach_iterations`, `orchestrator_call_policy`, `orchestrator_agent` and `decision_router` are read by the engine; any other settings key is dead.

## Save-time error copy

`FlowDefinition.validate` never shows validator codes. `huf/ai/graph/error_copy.py` maps each failure to a plain sentence naming the step and field (e.g. "Step 'approval_1' (Human Approval): who can approve is required. Open the step and fill it in.", "Step 'n3' is not connected to the start of the flow. Connect it or delete it.").
