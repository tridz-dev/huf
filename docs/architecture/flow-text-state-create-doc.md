# Flow: text ops, templates, state, create-doc

Deterministic (no LLM) building blocks for Flow. Schema: `huf/ai/graph/graph_ir.schema.json`.

**Text transform ops** (`transform` node, `config.op`; inputs bounded to 10,000 chars; null -> "", numbers stringified):
`lower`, `upper`, `trim` (`text`); `replace` (`text`, `find`, `with`, `count?`); `contains` (`text`, `needle`, `ignore_case?`) -> bool;
`starts_with` (`text`, `prefix`, `ignore_case?`) -> bool; `split_first` (`text`, `separator?`); `regex_extract` (`text`, `pattern`, `group?`, `default?`);
`concat` (`parts`, `separator?`). `regex_extract` accepts a conservative subset only: pattern <= 200 chars, no lookaround/named groups,
no backreferences, no quantified groups. (The row op `join` is unchanged; text joining is `concat`.)

**Templates**: `{"$template": "Refund for #{order}", "vars": {"order": {"$from": "x.y"}}}` anywhere a `$from` is allowed.
`{{`/`}}` are literal braces. Undeclared placeholder or malformed braces fail the node; a var that resolves to null renders as "".
bool -> true/false, list/dict -> compact JSON. Rendered output <= 10,000 chars.

**State** (`state.get` {key, default?} -> {found, value}; `state.set` {key, value, ttl_seconds?}; `state.delete` {key} -> {deleted}):
stored in `Flow State` (flow_id, state_key, value_json, expires_at). Scoped to the running flow (no cross-flow access, config cannot name a flow).
Default TTL 24h, max 30 days, value <= 16 KB, key <= 140 chars. Expired rows read as missing and are purged lazily and by the daily
`huf.ai.flow.state.purge_expired`. Gateway-triggered runs carry `gateway`, `sender_id`, `conversation_id` (use `input.sender_id`).
Doctype access: System Manager / Huf Manager only; flows reach it through `huf.ai.flow.state`.

**doc.create** {doctype, fields} -> {doctype, name}: doctype must be in site config `huf_flow_create_doc_doctypes` (default `["ToDo"]`);
inserts as the run's session user with normal permission checks (no `ignore_permissions`); scalar values for existing, writable,
non-system data fields only; counts against `contract.limits.max_writes` per run (0 or absent = no writes).

**Conditions** can read earlier node outputs: `context["outputs"]["<node_id>"]`.
