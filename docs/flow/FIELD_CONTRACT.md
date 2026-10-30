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
| | | `secret` | string | yes | length 32-256; the receiver compares the `X-Huf-Secret` header to this value (constant time), fail closed. A secret in the URL (`?secret=`) is not accepted |
| Schedule | `trigger.schedule` | `cron` | string | yes | min length 1; 5-part cron (`minute hour day month dow`; numbers, ranges, steps, lists, names, `L` for the last day of the month), read on the clock of `time_zone` |
| | | `time_zone` | string | no | IANA name such as `Asia/Kolkata`; absent means the site time zone. Checked with plain sentences when the flow is made live (`support/schedule_rules.py`) |
| Data (doc event) | `trigger.doc-event` | `doctype` | string | yes | min length 1, literal |
| | | `event` | string | yes | enum `after_insert`, `on_update`, `on_submit`, `on_cancel`, `on_trash` |
| (placeholder, not runnable) | `trigger.unset` | none | | | empty config; cannot activate |

Notes:
* `auth`, `apiKey`, `webhook_key`, `intervalType`, `interval`, `cronExpression`, `schedule_name`, `timezone` (the key is `time_zone`), `filters`, `PUT`, `DELETE`, `on_delete` are all invalid. The UI compiles any "every N hours/days" picker to a cron string before saving. The optional `time_zone` is consumed by `run_due_schedule_flows`, which reads each cron on that zone's clock.

Every node may also carry `_sample` (UI extra like `_label`) and `_sample_at` (ISO time it was pinned): a pinned example, at most 8 KB, passwords and keys hidden. On a trigger it is the data the flow starts with (an object: a sample request). On any other step it is what the step **produced** when it was tested, as the step gives it (an object, a list or text; see section 12). Only people who can edit the flow get it back from the server; run snapshots never keep it, a copy of a flow drops it, and the server shrinks an oversized `_sample` on every save.
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
| Human in Loop | `human.approval` | `message`* string, `approve_next`* id, `reject_next`* id, `timeout_next` id, `timeout_ms` int >=1, `approver_type`* enum `role`/`user`, `approver_role` string (required when `role`), `approver_users` array of string (min 1, required when `user`), `title` string (1-120, placeholders allowed: the card's headline), `details` array (max 6) of `{label?: string 1-60, value*: Value}`: the facts the approver sees (section 11.2). No `next`. |
| Transform Data | `transform` | `op`* enum (below), `input`* object of Value |
| Execute Code | `code.run` | `code`* string (Python, at most 64 KB), `profile`* string (name of an Execution Profile; default `Flow Scratch`), `inputs` object of Value (handed to the code as the `inputs` variable: data only), `timeout_s` int >=1 (at most the profile's wall limit). Needs both code switches and the capability `flows.execute_code`, see section 10. A `tool.call` naming `run_python` stays refused at run time. |
| Send Email | `tool.call` | `tool_id` `gmail_send_email`; `input` `{to*, subject*, body*}` |
| HTTP Request | `tool.call` | `tool_id` `http_request`; `input` e.g. `{url*, method, headers, body}`. **Tool not registered, see section 6.** |
| File Operations | `tool.call` | `tool_id` one of `gdrive_list_files` (`limit`, `query`), `gdrive_search_files` (`query`*), `gdrive_get_file` (`file_id`*) |
| Slack | `tool.call` | `tool_id` `slack_send_message`; `input` `{channel*, text*}` (also `slack_send_thread_reply` with `thread_ts`*) |
| Google Sheets | `tool.call` | `tool_id` `gsheets_read` (`spreadsheet_id`*, `range`), `gsheets_update` (`spreadsheet_id`*, `range`*, `data`*), `gsheets_create` (`title`*) |
| End | `output` | `value`* Value, `outcome` `{label?: string 1-60, tone?: good/neutral/bad}` (section 11.3). No `next` key at all (not even null). |
| Get / Set / Delete state | `state.get` / `state.set` / `state.delete` | get: `key`* Value, `default` Value; set: `key`*, `value`*, `ttl_seconds` int 1-2592000 or Value; delete: `key`* |
| Create document | `doc.create` | `doctype`* string literal (must be in site allow-list `huf_flow_create_doc_doctypes`), `fields`* object of Value |
| (assertions) | `validate` | `assertions`* array (min 1) of `{expression*, code*, message*}` |

`tool.call` UI presets (Email, Slack, Sheets, File, HTTP, Code) are `tool.call` and carry ONLY
`tool_id`/`input` (+ optional `timeout_ms`, `approved`). The legacy `tool_name`, `args`,
`parameters`, `output.save_result_to_context`, `mcp_server`, `agent_name`, `gateway` keys are rejected by the schema.
`router.llm.prompt` and `human.approval.message` are plain strings; `{input.field}`, `{trigger.x}`, `{<node_id>.field}` and `{foreach.item}` placeholders in them are filled in at run time (`engine.render_text_refs`); a placeholder that does not resolve is left as written.
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
        "secret": "change-me-webhook-secret-0123456789abcdef"
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

1. **Execute Code**: resolved (WP19). It is its own node type, `code.run`, with an Execution Profile (section 10). A `tool.call` naming
   `run_python` is still refused at run time (`huf/ai/tools/invocation.py`: Code Execution tools are only available to an agent run).
2. **HTTP Request**: resolved. Built-in tool `http_request` (App Provided, declared in `huf/ai/tools/_registry.py` `HTTP_TOOLS`, function `huf.ai.http_handler.http_request(url, method="GET", headers=None, body=None)`) matches the `input` contract `{url, method, headers, body}`. Returns a JSON string with `success` (true only for 2xx), `status_code`, `headers` subset, `body` (64KB cap), `truncated`.
3. **Gateway / MCP binding**: the engine reads `config.mcp_server` and `config.gateway` on `tool.call`; the schema forbids them. The engine
   must resolve MCP tools by unique tool id (`find_unique_mcp_server_for_tool`). `FlowDefinition._validate_gateway_authority` is therefore dead for saved flows.
4. **Backend consumers of the old names**: resolved. `flow_webhook` authenticates with the trigger node's `secret` (the `X-Huf-Secret` header only; the flow must be named by `flow_id`, it is never looked up by its secret; 60 calls a minute per caller address, then 429), the engine reads only the contract names (`on_true`/`on_false`, `foreach` body fields, `tool_id`/`input`, `approver_*`), `get_pending_approvals` and the approve/reject endpoints read the `waiting` keys in section 7, and `huf/ai/gateways/approvals.py` reads `approver_type`. Legacy keys (`auth`, `apiKey`, `webhook_key`, `approval_type`, `title`, `instructions`, `true_node`, `iterate_over`, `tool_name`) are ignored.
5. `approver_type` is required by the schema (pre-release: no legacy approval nodes). `parallel` and `tool.call.recovery` are Flow-removed; they remain only in the Procedure profile.

## 7. Engine behaviour notes (verified against `huf/ai/flow/engine.py`)

**Templating and expressions**
* `{{var}}` is NOT supported anywhere. In `agent.run.prompt`, `{name}` placeholders are filled from `prompt_bindings`; `{{`/`}}` are literal braces. Other dynamic values use `{"$from": ...}` or `{"$template": "...", "vars": {...}}`.
* `router.llm.prompt` and `human.approval.message` are plain text: no placeholders are substituted.
* `condition` expressions use `input[...]` roots (AST-restricted evaluator). The only calls allowed are `number(x)`, `lower(x)`, `startswith(x, y)` and `endswith(x, y)` (fixed names and argument counts, total: wrong types give null / false). The Condition builder writes and reads exactly the shapes of `docs/flow/CONDITION.md`.

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

## 8. Engine behaviour notes added by WP1 (supersede the matching lines of sections 2, 6 and 7)

**Triggers.** The only trigger path is the dispatcher in `huf/ai/flow/triggers.py` (`run_due_schedule_flows`, `run_doc_event_flows`, the webhook receiver). `set_flow_trigger` / `get_flow_trigger` / `clear_flow_trigger` and the Automation they created are removed; mentions of them in section 2 are obsolete. A schedule fires one Flow Run per (trigger node, due minute).

**Scheduler tick.** Frappe's scheduler wakes every `scheduler_tick_interval` seconds (default 240). Only `common_site_config.json` is honoured (the scheduler process has no site; a value in a site's `site_config.json` is ignored). `huf.install.after_migrate` sets it to 60 in the common config when the bench has no value; the running `bench schedule` process must be restarted once to pick it up. Approval timeouts are also expired lazily: every read of a run waiting for approval (`get_flow_run`, run lists, `get_pending_approvals`, the agent tool) first routes an overdue approval along `timeout_next`.

**Failed step record.** When a node fails (returns `failed` or raises), its stored output becomes `{"status": "failed", "error": "<readable reason>"}` (any other keys the node returned are kept). It is read at `context_json.__node_outputs__["<node_id>"].error` (`get_flow_run` -> `context_json`), and a later node can reference it like any output. A raised exception now fails the node (so `on_error` applies) instead of aborting the run.

**Approval decision record** (the approval node's output): `{"decision": "approved" | "rejected" | "timeout", "comment", "decided_by", "decided_at"}`. `approved_by` / `approved_at` no longer exist. A timeout record has `decided_by: null` and `decided_at` set to the expiry time. `decided_at` is a time-zone-aware UTC string (`2026-10-28T02:49:20Z`).

**`router.llm` output**: `{"label", "node_id", "reason", "model", "provider"}`. `model` is the AI Model used (the configured `model`, else the provider default), or the one attempted when the call failed.

**`tool.call.timeout_ms`** ("Wait up to") is enforced for MCP tools only: past it the step fails with "timed out after N ms". Built-in tools ignore it, because they run on the worker's Frappe request context (thread-bound DB connection and transaction) and cannot be abandoned or cancelled safely from a helper thread.

**Run settings are gone.** The graph has no `settings`; the engine reads none. Every run uses the engine default hop budget (100) and a shared conversation; `foreach` is bounded by `config.max_iterations` and `contract.limits.max_foreach_iterations`. Agentic mode / orchestrator agent and the `decision_router` adapter are removed (`router.decision` always routes to its `default`). `run_flow` no longer accepts `mode` / `conversation_mode`.

**Stale runs.** `huf.ai.flow.engine.sweep_stale_runs` (every 5 minutes) fails a Flow Run left in Queued/Running with no change for 30 minutes (`STALE_RUN_SWEEP_MINUTES`) and no live run lock, with last_error "Run did not complete (worker stopped)". Waiting runs are never swept. Manual "Mark as failed" is in `api.py` (WP5).

**`router.llm` context.** The model is shown the workflow input and the outputs of the steps that already ran (`{"input": ..., "steps": {<node_id>: <output>}}`, truncated to 4000 characters), so a router placed after a Run Agent step can route on that step's reply.

**Integration credential errors.** A tool step that fails because an integration is not connected reports "`<Integration>` is not connected. Connect it in Integrations." (`huf.ai.flow.integrations.friendly_tool_error`) instead of the internal credential key and environment variable name. The Run details step card adds a Connect link for it.

**Performance notes (WP10).** A trivial flow takes about 0.2 s end to end from the queue; the ~7 s seen in journeys had three causes:
- *Cold imports in every background job.* Frappe's `bench worker` forks a fresh work horse per job, so modules imported by an earlier job are gone. The first document write in a job loaded `huf.ai.agent.hooks`, which imported `huf.ai.agent.integration` and with it litellm, the agents SDK, llama_index and nltk: about 3.4 s of a 3.9 s tool step. Fixed in app code: `agent/hooks.py` imports `run_agent_sync` only where it runs an agent, and `mcp_client.py` no longer imports the agents SDK at module level (a tool step now costs about 1.3 s cold, 0.07 s warm). The remaining ~1.1 s is `sdk_tools` (agents SDK) loading for the first built-in tool call of a job; removing it needs a worker that preloads the SDK in the parent process before forking (a Frappe worker setting, not app code).
- *One worker for every queue.* `uiverify-huf` runs `background_workers: 1` and a single `bench worker` consuming `default`, `short` and `long`, so a run queued behind a 20 to 30 s agent run waits for it. Production benches should run one worker per queue (`bench worker --queue default`, `--queue long`) or more than one worker.
- *No needless waits in the engine.* Measured creation to completion with timestamps: queue pickup (enqueue to start) is under 50 ms (Redis blocking pop, no polling interval); enqueue itself is about 12 ms; `run_flow` for transform or condition steps is a few milliseconds per node; there are no sleeps, and commits are one per node. Manual runs from the Run button execute inside the request (about 15 ms for a trivial flow).

## 9. Security and concurrency rules added by WP11

* **Webhook.** The secret travels only in the `X-Huf-Secret` header (32-256 characters; the editor generates 48). `?secret=` is not accepted. The flow is always named (`flow_id`, `?flow_id=` or `X-Huf-Flow-Id`); a flow is never looked up by its secret. Both endpoints allow 60 calls a minute per caller address and then answer 429. Unknown flow, unpublished flow, wrong or missing secret all answer the same 403.
* **Approvals and resume.** `approve_flow_run` / `reject_flow_run` / `resume_flow_run` / the timeout sweep take the run lock, re-read the status under it and leave `Waiting Approval` / `Waiting User` with one conditional `UPDATE ... WHERE status = ...`. Exactly one of any number of simultaneous callers wins; the rest get a plain "already decided" message and nothing runs twice. A decision on an approval whose deadline has passed is refused ("This approval has expired"); the timeout path owns it.
* **Terminal statuses.** `Success`, `Failed` and `Cancelled` are final. Every engine write that ends a run (complete, fail, "Mark as failed", the stale sweep) is conditional on the run not being final already, so a live worker cannot be overwritten and a finished run cannot be failed. "Mark as failed" takes the run lock and refuses while a worker holds it.
* **Publishing sensitive flows.** A flow with a `trigger.doc-event` or a web request step (`tool.call` of `http_request`, or any GET / POST tool) can only be Active if the saving user holds the capability `flows.publish_sensitive` (Huf Manager and Huf Admin by default; add it to a custom Huf role on purpose). The check runs in the Flow Definition validator, so `publish_flow` and any direct save enforce it. Editing an unrelated step of an already-published flow does not need it; adding or changing a sensitive step does. A document-event flow also stops firing while its owner lacks the capability or is disabled.
* **Document-event payload.** The run starts with the document as its owner may read it: fields above the owner's permission level and Password fields are removed, also in child rows. The lookup cache is cleared on Flow Definition save / publish / unpublish and on User and Has Role changes.
* **Web requests** resolve the host once, require every returned address (IPv4 and IPv6) to be public, and connect to those addresses (the URL host still drives `Host` and TLS). Each redirect hop is resolved and checked the same way. With an HTTP proxy configured in the environment the proxy resolves names itself and pinning does not apply.

## 10. Execute code in Flows (WP19)

Node `code.run`: config `code`* (string, at most 64 KB), `profile`* (Execution Profile name), `inputs` (object of Value), `timeout_s` (int >= 1, at most the profile's `max_wall_time_s`). It may carry `next` and `on_error` like any action. It cannot be inside a loop body.

**Output** (`{"$from": "<node_id>"}`): `{"stdout": str, "result": any JSON, "exit_status": "Ok"|"Timeout"|"OOM"|"Error"|"Killed", "truncated": bool}`. `result` is the value of the variable `result` at the end of the code. `truncated` is true when stdout or `result` was cut at the profile's `max_output_bytes`. A failed step's output is the same four keys plus `status: "failed"` and a plain `error`; `on_error` / `on_failure` routing applies. In the code: `print()` goes to `stdout`; `inputs` is a dict of the mapped inputs; nothing can be imported unless the profile lists the module; with a `Scratch Only` profile `open("name.txt", "w")` works inside a flat private folder (no subfolders, no absolute paths) that is deleted when the step ends; there is no network.

**Two switches, both off by default; both must be on to publish or run a code step.** The server switch (site config `huf_python_execution_enabled`, set with `bench set-config`) and `Agent Settings.allow_code_in_flows` (only a System Manager can change it: field permission level 1). `huf.ai.flow.code_node.get_code_flow_status` reports both for the editor.

**Trust rule.** Code and profile are read from the definition the run pinned at start, never from run input; `inputs` reach the code as JSON data only. A run of a flow with a code step can only start from an Active (published) flow. Saving a new or changed code step needs `flows.execute_code` (also as a draft); making it Active also needs `flows.publish_sensitive`, both switches on, a usable profile (enabled, not `Never Allow`, not `Shared Directory`) and a time limit within the profile's. `flows.execute_code` is held by System Manager and Huf Admin by default. At run time the flow owner must still hold `flows.execute_code` and `code_execution.run`, and both switches must still be on; otherwise the step fails with a plain message.

**Running.** The code runs in a background worker (queue `long`, or site config `huf_flow_code_queue`) or waits behind an Agent Execution Approval (profile `Ask Every Time`). The Flow Run is `Waiting Code` meanwhile (`waiting`: `{type: "code", node_id, agent_tool_call, agent_run, approval, timeout_at, message}`); the worker finishing, an approval decision or its expiry continues it, with the sweeper (every minute) as the safety net. One `Agent Tool Call` audit row is written per execution (profile snapshot and code hash; the code itself is never stored there), linked through the step's Agent Run to the Flow Run. One run may execute at most 20 code steps. Built-in profile `Flow Scratch`: Auto Approve, Scratch Only, no network, 30 s wall, 30 s CPU, 256 MB, 256 KB output.

**Expression limits (security round 2).** Conditions, checks and the shared expression language never repeat text or lists (`"ab" * 3`, `[0] * n`, `"%5d" % x` are refused), integers must stay below 10**18 in every operand and result, and a joined text or list may not pass 1,000,000 characters or items. A step that hits a limit fails with: "This check works with numbers or text that are too large to calculate safely. Use smaller numbers, and do not repeat text or lists." Elsewhere (row filters, Procedure conditions) the answer is simply "no"/false, so a check that hits a limit fails closed instead of allocating memory.

## 11. Test run, approval card and run outcome (UX-14 / UX-15)

### 11.1 Test run (`run_mode`)

A run is **Real** (default) or **Test**. `Flow Run.run_mode` (Select `Real` | `Test`, read-only) is set when the run is created and read by every continuation (approval, resume, code step, timeout sweep); nothing else carries the mode.

* API: `huf.ai.flow.api.run_flow(flow_id, payload, mode="real")` takes `mode` = `"real"` | `"test"` (anything else is refused with a plain sentence). `huf.ai.flow.engine.create_flow_run(..., mode=...)` is the same switch. Webhook, schedule, document-event and gateway runs are always Real.
* Responses: `get_flow_run` returns `run_mode` (`"Real"` | `"Test"`). `list_flow_runs`, `list_flow_runs_page` rows carry `run_mode`; `list_flow_runs(..., run_mode="real"|"test")` filters. The flows list ("last run" on a card) and the dashboard run counts ignore Test runs.
* What a test run does, node by node: `tool.call` of a tool classified `reads` runs for real; `changes` and `sends` are **skipped** and the step succeeds with a simulated output. `doc.create` is skipped. `code.run` runs for real only in profile `Flow Scratch` as shipped (a scratch folder, no network policy, no importable modules, no shared folder); any other profile, or a `Flow Scratch` that an administrator gave a network policy, modules or a shared folder, is skipped (`huf.ai.flow.testrun.gate.code_profile_is_scratch`; an unreadable profile is skipped too). The Run dialog says so: "Code steps with network access are skipped in a test run." Conditions, loops, transforms, `state.*`, routers, `validate`, `output` and **agents** run for real; an agent's tools follow the same rule (a `changes`/`sends` tool, native or MCP, answers with the simulated output instead of running). `human.approval` pauses for real.
* Simulated output (what later steps read as `{"$from": "<node_id>"}`): `{"simulated": true, "summary": "Would send email to ada@example.com", "note": "Skipped in a test run: nothing was sent or changed.", ...sample fields with the real tool's names}`. A skipped `doc.create` returns `{"simulated": true, "summary", "doctype", "name": "(sample) ToDo"}`; a skipped `code.run` returns `{"simulated": true, "summary": "Would run your code", "stdout": "", "result": null, "exit_status": "ok", "truncated": false}`. A step that was skipped is recognised by `simulated: true` in its output.
* Approval in a test: the pause is real, `waiting` gets `test_run: true`, `test_note: "Test: you can approve this yourself"`, `test_owner: <user who started it>`. The approver check still applies, and in a test the person who started it may also decide. No email and no Slack card is sent; the person who started the test gets an in-app bell entry "Test: ...". `get_pending_approvals` lists a test approval for that person.
* **Fails closed.** Every place that decides test-or-real answers "test" when it cannot tell: `gate.agent_run_is_test` (a failed Agent Run / Flow Run lookup), `gate.step_test_active` (flag unreadable) and `gate.simulate_node` (a tool step whose inputs cannot be resolved is classified by its typed-in settings, so a send is still skipped). Each doubt is logged (`huf` logger, "treating the call as a test").
* Tool classification: `huf/ai/flow/testrun/effects.py` (`TOOL_EFFECTS`, `tool_effect(tool_id, args, tool_type)`). Every tool of `ALL_INTEGRATION_TOOLS` and the gateway tools is listed explicitly (a test asserts it). Unlisted tools (custom, MCP, new) count as `changes`; a custom tool is classified by its Agent Tool Function type (Get Document / GET / ... = reads, Send Email = sends). `http_request` is `reads` for GET and HEAD only. Multi-action tools (CRM, ERPNext, Telegram, WhatsApp, Raven ...) are classified by their `action` argument. `list_flow_tools` returns `effect` for each tool.
* Run dialog contract: `run_flow` is called with `mode`. The dialog builds its form from `contract.input_schema.properties` (`title`, `type`, `example` per property) when there are any, otherwise from the trigger node's `_sample`.

### 11.2 Approval card (`title`, `details`)

`human.approval` takes two optional settings: `title` (string, 1-120, `{input.field}` placeholders are filled in) and `details` (array of at most 6 `{label?, value}`; `value` is normally `{"$from": "input.amount"}`, and every reference must point at the trigger input or an earlier step, like any other reference). When the run pauses the engine builds ONE card and stores it in `Flow Run.waiting` (`card_title`, `message`, `facts`); the bell, the run page, the email and the Slack message all render that card, nothing else.

* **Facts.** With `details`: each row is `{label, value}` where `label` is the author's `label`, else the field's title from `contract.input_schema.properties[<field>].title`, else the field name in words ("order_amount" is "Order amount"; a nested field reads as its parent: "customer.name" is "Customer"); `value` is the data as a person reads it (a record becomes "Ada Lovelace", a list "3 items", true "Yes", a date "29 Oct 2026"). A detail that is empty or does not resolve leaves no row. Without `details`: the few most telling facts of the run's input (as before), also labelled from the contract titles.
* **Title.** `title` rendered, else "Approval needed: <flow name>". **Note.** The step's `message` (rendered), else "<flow name> is waiting for your decision."
* **API.** `get_flow_run` returns `approval_card` while the run waits for approval (else `null`); every row of `get_pending_approvals` returns it too. Exactly: `{"title": str, "facts": [{"label": str, "value": str}], "note": str, "test_note": str | null}`. `test_note` is "Test: you can approve this yourself" for a test run. `get_pending_approvals` also keeps `title`, `message` (one sentence: note, facts and, in a test, the test note) and `facts` for the existing bell.
* Email subject and bell entry are the title; the body is the note, then a table of facts, then the "Review and decide" link. The Slack card is the title, the note and one "Label: value" line per fact. No run id, step id, JSON or raw reference ever appears in any of them. A test run sends no email and no Slack card.

### 11.3 End outcome (`output.outcome`)

An `output` (End) node may declare `outcome: {label, tone}`: how the run reads to the business ("Approved", "Rejected", "Refund sent"). `label` is 1-60 characters (`{input.field}` placeholders are filled in when the run ends; absent: "Finished"), `tone` is `good` (green), `neutral` (grey, the default) or `bad` (red). Both are optional; `outcome: {}` means "Finished", neutral.

* **Recorded.** When the run reaches that End step the engine writes `Flow Run.outcome_label` and `Flow Run.outcome_tone` (a test run records it too). An End without `outcome` records nothing.
* **Served.** `get_flow_run`, `list_flow_runs` and `list_flow_runs_page` return `outcome: {"label": str, "tone": "good"|"neutral"|"bad"} | null` for a finished (Success) run: the recorded outcome first, else (End without outcome) what an approver decided ("Approved" good, "Rejected" bad, "Timed out" neutral), else null. A Failed or unfinished run has no outcome; the status says it. The row fields `outcome_label` / `outcome_tone` are not part of the response.
* **Showing it.** The run headline uses the label ("Rejected", bad tone) with the small "Run finished" line under it; the outcome chip beside the status in Run history and Executions uses the same label and tone.

## 12. Testing one step, pinned samples (UX-16)

### 12.1 API (`huf.ai.flow.testrun.step_test_api`, editors only: write permission on the flow)

* `get_step_test_info(flow_id, node_id)` -> `{kind, effect, calls_ai, simulated, approval, trigger, trigger_kind, doctype?, parts, sample_input}`. `effect` is `reads` | `changes` | `sends` (`huf/ai/flow/testrun/effects.py`). `parts` is the data the step receives, for display: `[{key, title, kind: input|step|item, source: pinned|trigger_sample|last_run|none, value, shortened, ran_at}]`. `key` is `input` (what the flow starts with: the trigger's `_sample`, else the latest successful run's payload), a step id (that step's `_sample`, else its output in the latest successful run) or `item` (first item of the enclosing loop's list). Only steps the step's settings mention are listed. `sample_input` is `{input, steps: {<step id>: output}, item?}`, the same data as one object.
* `test_step(flow_id, node_id, sample_input=None)` (POST) runs ONE step against `sample_input` (this shape, 64 KB at most; absent: the sample of `get_step_test_info`) and returns `{status: success|failed, mode: real|simulated|preview, output, output_shortened, pin_value, duration_ms, error, fix_hint, tested_at, effect, calls_ai, summary, preview, goes_to, branch}`. No Flow Run is created and nothing is stored: the run history never shows a step test. A **slow** step (agent, AI router, loop, web read) is queued and the request returns at once `{status: "running", token, poll_after_ms: 1000, wait_up_to_s: 35}` (it never waits for the queue); quick steps answer in the request.
* `get_step_test_result(token)` (editors only, and only the person who started that test) -> the same result shape, or `{status: "running", ...}` again, or a plain failure ("The test could not start because the background worker is busy. Try again in a moment.", "This step took longer than 30 seconds, so the test was stopped.", "This test is no longer available. Run it again."). The answer is kept 5 minutes (redacted and size-capped exactly as `test_step`'s). The page asks once a second for up to 35 seconds, stops when the person leaves the step, and then says "The background worker is busy: try again".
* `list_recent_documents(flow_id, node_id)` -> the five most recently changed documents of a data trigger's type that the caller may open; `get_document_sample(flow_id, node_id, docname)` -> `{sample}` as the flow would receive it (fields the caller may not read are left out).
* Limits: 20 tests a minute per person (then a plain "You are testing steps very quickly"; polling does not count); 30 seconds per step (steps that can be slow, meaning agents, AI routers, loops and web reads, run in a `short`-queue job that is stopped at 30 s); output at most 64 KB with secret-looking keys and token-shaped values hidden; `pin_value` at most 8 KB.

### 12.2 What runs

A tool step whose deciding setting (`action`, or an HTTP request's `method`) is filled in from other data is labelled `changes` (simulated) in the Test tab before it runs, because what it will do is not known until it runs (`step_test.describe_step`).

Conditions, loops, transforms, checks, End, "Use saved data" and every tool classified `reads` run for real. A tool step that `changes` or `sends`, a record creation, "Save data for later" / "Forget saved data" (also inside a loop) and a code step answer with the simulated output of section 11.1 (`mode: simulated`, `summary`: "Would send email to ..."); a code step is only ever run by a full test run. An agent or an AI router makes a real call to the AI model (`calls_ai: true`); an agent's tools follow the same rule as in a test run. "Wait for approval" returns `mode: preview` and `preview: {title, note, facts, who_can_decide}`, the card the approver would get; it never pauses and nobody is told. Triggers: schedule -> a simulated tick `{scheduled_for, trigger_node, cron}`; webhook -> the last received request; data trigger -> the newest document you can open (or the one given in `sample_input.input`).

### 12.3 Pinned samples (shape for the Use-data picker)

"Pin this output" stores `pin_value` of the last test as the step's `_sample` (and `_sample_at`) through the normal flow save. For a simulated step the "Would ..." wording is left out and the sample fields (`id`, `ts` ...) stay. The picker (`catalog.api`) reads `_sample` of an earlier step as **its output**: an object gives its fields under `<step id>.<field>`, a list or text gives the step's result as a whole. A trigger's `_sample` is `input`. Samples are request data: viewers never get them (`drop_samples`).

## 13. Step forms (UX-12)

* **Placeholders in plain-text fields.** `render_text_refs` (the approval `message` and `title`, the router `prompt`, the End `outcome.label`) fills `{input.field}`, `{<step id>.field}` and `{foreach.item}`. It also takes a wording prefix: `{table:input.order}` (a record as `Label: value` rows), `{joined:n1.items}` (a list joined with commas) and `{count:n1.items}` (how many). They read exactly like the template variables `table_x`, `joined_x`, `count_x` (`huf.ai.graph.templates.render_marked`). In an approval request the message is written as one sentence ("Name: Ada Lovelace Email: ada@example.com"), never JSON.
* **Approvers who do not exist.** Saving or publishing lists `approver_users` that no enabled user has as something to finish (`UNKNOWN_APPROVER`, "no one here is called ..."). A run does not re-check people (`validate_flow(..., check_people=False)`), so a test run of a draft may name anyone. The editor offers people through `huf.ai.flow.catalog.form_options_api.search_flow_users` and checks saved names with `check_flow_users`.
* **Create document.** The editor lists the kinds of record the site allow-list permits and the person may create (`get_create_document_types`), then the fields the step may set (`get_create_document_fields`: not system, read-only, hidden, layout or attachment fields; required first).
* **The time limit and the Timed out path.** `timeout_next` is written only while `timeout_ms` is set; clearing the time limit in the editor removes the Timed out connection (after asking when a step is connected).
* **Send to / Subject / Message, Sheets and Drive.** A pasted Google link becomes the id (`/d/<id>`, `?id=<id>`); a pasted Slack message link becomes `thread_ts`.
