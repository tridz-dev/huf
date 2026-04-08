# Odoo Integration & Automation Landscape for AI Agent Platform

## Executive Summary

Odoo’s documented external integration surface for business objects is RPC-based (XML-RPC and JSON-RPC), with outbound, event-driven automation achievable via Studio Automation rules that can send HTTP `POST` webhook notifications containing selected record fields. citeturn21view0turn30view0 For Odoo Online (Odoo.com SaaS), Odoo’s own documentation emphasizes important constraints: external API access is only available on **Custom** pricing plans (not One App Free or Standard), and users on Online instances may need to set a local password for API access. citeturn16view0 A near-term strategic risk is that Odoo 19’s developer docs announce that the legacy `/xmlrpc`, `/xmlrpc/2`, and `/jsonrpc` endpoints are scheduled for removal in Odoo 20 (fall 2026), with an “External JSON-2 API” positioned as the replacement. citeturn16view0 The recommended platform approach for HUF is therefore a **hybrid**: build first-class RPC connectivity for Odoo 15–17+ now, implement webhook ingestion wherever customers can configure outbound webhooks, and keep a polling fallback; in parallel, start a roadmap for JSON-2 support to avoid a “cliff” as customers upgrade toward Odoo 20+. citeturn16view0turn18view0turn30view0

## API Landscape Table

The table below reflects what is explicitly documented as Odoo’s supported external interfaces (plus the forward-looking JSON-2 replacement) and what typically exists only as custom/third-party additions. citeturn21view0turn16view0turn30view0turn10view1

| API type | Endpoint pattern | Primary auth modes | Coverage (practical) | Key limitations / notes |
|---|---|---|---|---|
| XML-RPC | `/xmlrpc/2/common` + `/xmlrpc/2/object` | Database + login + password (API key can replace password); returns `uid` then call model methods | Broad access to model methods via `execute_kw` (CRUD + ORM methods) | Verbose payloads; requires careful pagination/field selection; **scheduled for removal in Odoo 20** (per Odoo 19 docs) |
| JSON-RPC | `/jsonrpc` | RPC “service/method/args” pattern (login via `common`, calls via `object`) | Functionally similar to XML-RPC; easier JSON transport | Also **scheduled for removal in Odoo 20** at `/jsonrpc` (per Odoo 19 docs) |
| External JSON-2 | `/json/2` | Documented as HTTP-based external API (“new in 19.0”) | Intended successor to the legacy external RPC endpoints | Only exists from Odoo 19+; your Odoo 15–17 target range won’t have it |
| “REST API” (generic) | Not natively documented as a general model API | N/A | Usually implemented via custom controllers or marketplace modules | Treat as “custom surface”, not a stable core integration contract |
| OData / GraphQL | Not natively documented | N/A | Usually third-party modules / custom | Treat as optional, customer-installed capability if present |

## Detailed Findings

**Odoo API surface (XML-RPC + JSON-RPC) and what “programmatic interaction” really means**  
Odoo’s official developer documentation presents external access as RPC interfaces (XML-RPC and JSON-RPC). citeturn21view0turn16view0 In the XML-RPC flow, a client authenticates against the “common” endpoint, then calls model methods through the “object” endpoint, most commonly via `execute_kw` to invoke ORM methods such as `search`, `read`, `search_read`, `create`, `write`, and `unlink` on a given model. citeturn18view0turn17view3turn22search2 The external API documentation explicitly highlights key operational concerns: a plain `read()` call can return “a huge amount” of fields unless you pass an explicit field list, and `search()` can return very large ID sets unless you use pagination parameters (`offset`, `limit`). citeturn18view0  

For JSON-RPC, Odoo’s Web Services documentation shows the `/jsonrpc` endpoint used with a JSON-RPC envelope and a service-style call pattern (`service=common` for login, then `service=object` for model method execution). citeturn21view0 In practice, XML-RPC and the documented JSON-RPC style are “transport choices” around the same conceptual interaction: remote invocation of the server-side ORM/model methods. citeturn21view0turn18view0

**Authentication options and how they vary by hosting model**  
Odoo’s External RPC API documentation (Odoo 19) contains two constraints that matter immediately for your “support Odoo Online + Odoo.sh + self-hosted” requirement:

- External API access is only available on **Custom** Odoo pricing plans (not One App Free or Standard). citeturn16view0  
- On Odoo Online instances (`<domain>.odoo.com`), users can be created without a local password (because login is via Odoo Online’s authentication), and the docs explicitly instruct setting a password on the user account to use XML-RPC. citeturn16view0  

Separately, Odoo’s “External API” reference documents API keys (introduced in 14.0) as a safer alternative to using the user’s main password for API access. citeturn3view1turn3view2 The n8n credential documentation reflects this in a productized integration context by recommending API keys and pointing to the Odoo UI path where “Developer API Keys” are created; it also notes that the option may require upgrading the Odoo plan. citeturn14view3  

For “where can I install custom modules,” Odoo’s official pricing page states that the Standard plan is hosted on Odoo Online “without custom modules,” while the Custom plan allows hosting on Odoo Online, on Odoo.sh, or self-hosting, and explicitly mentions Odoo.sh as “allowing you to develop or use custom modules.” citeturn27search25 This is a critical divider for your automation strategy: if you want deep event hooks via Python code, you should assume Odoo Online Standard cannot accept them, while Odoo.sh/self-hosted can. citeturn27search25turn27search1  

**Deprecation risk: Odoo 20 timeline and JSON-2**  
Odoo 19 developer documentation contains a high-impact warning: the XML-RPC and JSON-RPC APIs at `/xmlrpc`, `/xmlrpc/2`, and `/jsonrpc` are scheduled for removal in Odoo 20 (fall 2026), and the “External JSON-2 API” is presented as the replacement. citeturn16view0 For your platform, this implies that a “15–17+” connector that only supports legacy endpoints will likely face churn as customers upgrade. The official Odoo client library documentation also references the legacy XML-RPC/JSON-RPC methods and notes JSON2 usage for Odoo 19+, reinforcing that JSON-2 is being treated as a forward path. citeturn10view1

**Schema and model discovery: enabling agents to self-discover without hardcoding**  
Odoo’s external API reference shows concrete, supported introspection techniques that your agents (or a connector service acting on behalf of agents) can use:

- `fields_get` can retrieve field metadata for a model, with selectable attributes (e.g., `string`, `help`, `type`). citeturn17view0  
- `ir.model` can be used to create/discover models (and, by extension, list models if permissions allow). citeturn17view1  
- `ir.model.fields` is explicitly documented as the model that provides information about fields and allows adding custom fields without Python code; the doc notes limitations such as computed fields not being addable via `ir.model.fields` and some metadata (defaults/onchange) not being settable there. citeturn17view1  

From a platform design standpoint, the key implication is: you can build a “schema discovery & cache” layer that (a) enumerates available models for the integration user, (b) fetches field metadata via `fields_get`, and (c) uses that cache to validate tool schemas exposed to agents (and to generate guardrails like “required fields” and “field type constraints”). The external API docs also emphasize that naïve reads can fetch an excessive number of fields; your schema layer can proactively default to minimal field sets and only expand when needed. citeturn18view0

**Real-time triggers and event-driven automation: what’s actually available without custom code**  
Odoo’s Studio “Automation rules” documentation explicitly supports outbound event notifications via an action named “Send Webhook Notification.” It sends a `POST` request to a configured URL with the values of selected fields, and provides a “Sample Payload” preview. citeturn30view0 That same document enumerates core trigger types including “On create,” “On create and edit,” “On deletion,” and “On UI change,” and explains how “When updating field” selection affects repeated execution. citeturn29view3 It also describes the operational behavior of time-based triggers that are executed by a scheduled action, including a default frequency (every 4 hours) and an auto-increase in frequency for shorter delays. citeturn29view3  

This combination matters for Odoo Online customers where you cannot deploy modules: you can still get event-driven “push” behavior (webhook POST) for many business events by configuring Automation rules, and you can cover “delayed” workflows using the time-based trigger scheduling behavior described in the docs. citeturn30view0turn29view3  

For more complex outbound integrations, the same Automation rules page documents an “Execute Code” action that runs Python code with access to variables like `env`, `record`, and `records`. citeturn30view0 However, it also highlights that custom code maintenance is not included in Standard or Custom pricing plans and can incur additional fees—this is a practical adoption/operations constraint for customer success and “first-class automation” positioning. citeturn30view0  

**Polling as a fallback and how to do it safely**  
Given that not every customer will configure outbound webhooks (or may not trust them), polling must be first-class. The external API docs show enough primitives to build robust polling:

- Use `search()` with `offset` and `limit` to page through large result sets. citeturn18view0  
- Prefer `search_read()` as a server-side shortcut to reduce round-trips (search + read in one call). citeturn19view1turn17view3  

A practical “polling trigger” strategy (especially for Odoo Online constraints) is: poll `search_read` on key models with a domain constraint on a monotonic timestamp field (commonly `write_date` or an equivalent update marker), store a cursor (“last seen timestamp + tie-breaker ID”), and page deterministically with `order`/pagination when available. Odoo’s ORM documentation (older but consistent) explicitly states that `search()` can be ordered via an `order` parameter, and the external API doc confirms pagination support; together, these enable stable incremental scans. citeturn20search5turn18view0  

**Ecosystem: MCP, libraries, and integration platforms**  
MCP servers for Odoo do exist in the open ecosystem. A prominent example is the `mcp-server-odoo` project, which presents itself as an “Odoo MCP Server” supporting Odoo 13+ and connecting to an Odoo instance via extracted credentials (URL, db, username, password/API key). citeturn6view0 The same ecosystem also includes an Odoo Apps listing for an “Odoo MCP Server” module that advertises SSE, `tools/list`, `tools/call`, and a “resources” endpoint—meaning some vendors are attempting to embed an MCP server inside Odoo itself. citeturn4search20  

For client-side libraries, Odoo’s own documentation references high-level client libraries (including `odoorpc` under the OCA umbrella and `openerp-client-lib`). citeturn21view0 Additionally, Odoo publishes an official “Odoo Client Library” repository that explicitly documents support for both XML-RPC and JSON-RPC and mentions JSON2 usage for Odoo 19+. citeturn10view1 For async Python usage, `aio-odoorpc` on PyPI shows its last published release as 2.0.0 in April 2021, which is a signal that you should evaluate maintenance/compatibility carefully before standardizing on it for a production connector. citeturn32view2  

Integration platforms illustrate what “customers expect” from Odoo automation:

- entity["company","n8n","workflow automation company"] documents an Odoo credential type supporting “API key (Recommended)” and “Password,” and explicitly references Odoo’s External API documentation for further details. citeturn14view3  
- entity["company","Workato","automation platform"] positions Odoo connectivity as achievable via custom connections through an HTTP connector, and its app directory pages list standard ERP actions (e.g., confirm sales order, search records, update record, upsert record). citeturn15search3turn15search14  
- entity["company","Zapier","automation platform"] shows “Odoo ERP Self Hosted” workflows that trigger “when a new record is detected” and then create/update records, implying a polling-style trigger model when native push events aren’t present. citeturn15search15  
- entity["company","Make","make.com integromat"] provides Odoo integration documentation that reflects the same credential primitives (server URL, database, username, API key/password) and is therefore broadly consistent with an RPC-backed integration posture. citeturn11search24  

These platform patterns are useful benchmarks: customers will expect a combination of (a) “read/write actions” across core models and (b) “triggers,” often implemented via polling unless the source system offers an outbound webhook/event facility. citeturn15search1turn15search12

**Standard agents: what makes sense out of the box given the real capabilities**  
Given the RPC methods (`search`, `read`, `search_read`, `create`, `write`, `unlink`) and Automation-rule triggers (“create/edit/delete” and time-based) documented by Odoo, the most sensible “standard agents” are those that can (1) do deterministic CRUD, (2) summarize and route work based on retrieved records, and (3) optionally react to webhook/polling events. citeturn18view0turn17view3turn29view3turn30view0  

A compact blueprint for your initial pack:

| Standard agent | Primary Odoo models (typical) | Core API methods | Trigger options into HUF | Minimum privileges to be useful |
|---|---|---|---|---|
| CRM Agent | `crm.lead`, `crm.stage`, `mail.activity` | `search_read`, `create`, `write` | Outbound webhook on lead create/update; polling leads by update timestamp | Read/write on leads; create activities |
| Sales Order Agent | `sale.order`, `sale.order.line`, `product.product` | `search_read`, `create`, `write` | Outbound webhook on quotation/order events; polling for status changes | Read/write on sales; read products/pricing |
| Invoice Agent | `account.move`, `account.payment` | `search_read`, `create`, `write` | Time-based triggers (e.g., reminders); polling for unpaid invoices | Accounting read/write as permitted |
| Inventory Agent | `stock.picking`, `stock.move`, `stock.quant` | `search_read`, `write` | Outbound webhook on picking state change; polling transfers | Inventory read/write per warehouse rules |
| Helpdesk Agent | (often `helpdesk.ticket` where available) | `search_read`, `create`, `write` | Outbound webhook on ticket create/update; polling open tickets | Helpdesk app permissions |
| HR Agent | `hr.employee`, `hr.leave` | `search_read`, `create`, `write` | Webhook/polling on leave requests | HR read/write; restricted access compliance |
| Reporting Agent | cross-model (read-only) | `search_read` + aggregation via server-side methods | Scheduled triggers to refresh KPIs; manual chat | Read access across target models |
| Admin Agent | `res.users`, `res.groups`, system models | `search_read`, `write` (guarded) | Manual only by default | Elevated admin rights; strong guardrails |

This table is deliberately framed as “typical” because Odoo’s own documentation stresses that actual models/fields/methods vary by database and installed apps; your platform should validate model availability dynamically via discovery (`fields_get`, `ir.model`, `ir.model.fields`). citeturn17view0turn17view1turn20search23

## Architecture Decision Record

**Decision: Treat Odoo integration as a first-class “RPC + Events” connector, not as a REST connector**  
Odoo’s own documentation frames external integration around XML-RPC and JSON-RPC. citeturn21view0turn16view0 While custom REST endpoints can exist, they are not a stable, universal contract across Odoo Online/Odoo.sh/self-hosted installations, and therefore shouldn’t be the primary integration mechanism for a multi-tenant automation platform targeting unknown customer configurations. citeturn21view0turn27search25  

**Decision: Build with a deprecation-aware roadmap (JSON-2 readiness)**  
Because Odoo 19 explicitly announces endpoint removal in Odoo 20 (fall 2026) for `/xmlrpc*` and `/jsonrpc`, HUF should treat JSON-2 support as a planned milestone, even if Odoo 15–17 are the immediate scope. citeturn16view0turn10view1  

**Decision: Use webhooks where customers can configure them; polling as mandatory fallback**  
Odoo Studio Automation rules support outbound webhooks with selected fields using “Send Webhook Notification.” citeturn30view0 This is the best “no-custom-module” path for Odoo Online customers. Polling must still exist because not all customers will configure webhooks, and many integration platforms implement triggers via polling when webhooks are absent. citeturn17view3turn18view0turn15search12turn15search15  

**Decision: Offer an optional “event emitter module” only for Odoo.sh/self-hosted**  
Odoo’s pricing and hosting guidance draws a clear line: Standard Odoo Online is “without custom modules,” while Custom plan customers can use Odoo.sh or self-host and develop/use custom modules. citeturn27search25turn27search1 For those deployments, a small module can provide richer and more reliable events (e.g., signed payloads, resilient retries, broader coverage) than Studio webhooks alone, while keeping Odoo Online support intact via the Studio webhook + polling approach. citeturn30view0turn27search25  

```mermaid
flowchart LR
  subgraph Odoo
    E[Record event or time trigger]
    A[Automation Rules\nSend Webhook Notification]
    R[RPC API\nsearch_read / create / write]
  end

  subgraph HUF
    W[Webhook receiver]
    N[Event normalizer]
    P[Polling service\n(fallback)]
    S[Schema cache\n(fields_get, ir.model)]
    G[Agents + Flow Engine]
  end

  E --> A --> W --> N --> G
  R <--> G
  R --> P --> N
  S <--> G
```

## Build Backlog

**RPC Connector Core (M)**  
Implement a connector service that can call model methods (`execute_kw` equivalents) and supports both XML-RPC and JSON-RPC transports. citeturn21view0turn18view0 The service must support `limit/offset` paging, field selection defaults, and “safe read” patterns to avoid huge payloads. citeturn18view0turn17view3

**Credential & Auth Manager (M)**  
Support API keys as the default credential (where available) and document Odoo Online requirements (local password setup) and plan constraints (Custom plan requirement for external API). citeturn16view0turn14view3turn3view1

**Schema Discovery & Cache Layer (M)**  
Build discovery around `fields_get`, `ir.model`, and `ir.model.fields`, and expose a consistent internal schema to agents/tools. citeturn17view0turn17view1

**Webhook Receiver + Normalized Event Contract (M)**  
Implement an inbound webhook endpoint with signature verification, replay protection, and a mapping layer that converts Odoo webhook payloads (selected Fields) into a canonical HUF “record_event” envelope. citeturn30view0

**Polling Trigger Service (M)**  
Provide “watch model” triggers using `search_read` plus paging, with connector-level throttling/backoff. citeturn17view3turn18view0turn15search12

**Optional Odoo Event Emitter Module for Odoo.sh/self-hosted (L)**  
A lightweight module to emit signed webhooks for create/update/delete/state transitions, and to support richer payloads than “selected fields.” The business justification is strongest for Odoo.sh/self-hosted because custom modules are expected/allowed there. citeturn27search25turn30view0

**JSON-2 Support Spike (M → L depending on scope)**  
Prototype External JSON-2 API integration (Odoo 19+) and plan the migration path in anticipation of Odoo 20 removal of legacy endpoints. citeturn16view0turn20search23turn10view1

**MCP Strategy (M)**  
Because HUF already acts as an MCP client (per your architecture notes), evaluate whether to: (a) consume an existing Odoo MCP server, or (b) ship your own hardened MCP server that wraps your connector (recommended for consistent multi-tenant auth and governance). Existing MCP server projects and marketplace modules show this pattern is emerging but still early. citeturn6view0turn4search20

## Open Questions

- What is the exact practical availability of external API access across Odoo Online “Custom” tiers in real customer accounts, and are there region/contract exceptions beyond what the docs state? citeturn16view0turn27search25  
- For “Send Webhook Notification,” what are the operational semantics under failure (retry policy, backoff, timeouts, and whether delivery is queued vs synchronous)? The documentation confirms the POST + selected fields + sample payload, but not delivery guarantees. citeturn30view0  
- How quickly will customers in your target market adopt Odoo 20 once released, given the announced removal of `/xmlrpc*` and `/jsonrpc` endpoints in fall 2026? citeturn16view0  
- Which of your target “standard agents” require models or features that may be absent in some customer databases (due to app not installed or licensing), and what should the graceful degradation UX be when schema discovery indicates a model isn’t present? citeturn17view0turn20search23  
- What throttling characteristics should you assume for Odoo Online vs Odoo.sh vs self-hosted? Odoo’s docs do not publish numeric rate limits, so you’ll likely need empirical testing plus connector-level adaptive throttling. citeturn16view0turn18view0