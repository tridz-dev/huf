# **Odoo Integration & Automation Landscape for AI Agent Platform**

## **Executive Summary**

The architectural landscape for integrating autonomous artificial intelligence agents with Odoo environments is currently undergoing a profound systemic transition. Odoo is actively migrating away from its two-decade-old reliance on Remote Procedure Call (RPC) protocols—specifically the verbose XML-RPC and its undocumented JSON-RPC counterpart—in favor of a modernized, token-secured JSON-2 API introduced in Odoo 19\. This paradigm shift presents a complex dual-integration requirement for any AI agent platform attempting to provide comprehensive support across Odoo versions 15 through 19\. The research indicates that while legacy XML-RPC provides total coverage of the Object-Relational Mapping (ORM) layer, it imposes severe limitations on autonomous agents, including shallow relational data retrieval, Base64-encoded binary payload bloat, and rigid batch size caps that necessitate aggressive pagination. Conversely, modern JSON-2 implementations resolve these payload inefficiencies and introduce standardized HTTP status code error handling, which is critical for agentic self-correction. Compounding these protocol shifts are stringent deployment constraints enforced by Odoo's hosting models. Specifically, Odoo.com SaaS deployments entirely prohibit programmatic API access for organizations operating on the "Standard" or "One App Free" pricing tiers, gating integration capabilities strictly behind the "Custom" enterprise plan. Furthermore, the inability to install custom Python modules on SaaS environments forces the platform to rely on Odoo's native base.automation module for outbound event dispatching, utilizing dynamically executed Python scripts to construct and push tailored webhook payloads to the agent platform. To deliver first-class automation, the architecture must adopt a highly adaptive hybrid strategy: negotiating protocols dynamically based on the target Odoo version, utilizing deep runtime schema introspection via the ir.model.fields registry to map the entity-relationship graph without hardcoded logic, and deploying a tiered event-handling system that prioritizes customized webhooks where possible while falling back to intelligent, rate-limited polling mechanisms indexed against the write\_date field.

## **API Landscape Table**

| Protocol Interface | Authentication Mechanism | ORM Coverage | Capabilities, Limitations, and Version Compatibility |
| :---- | :---- | :---- | :---- |
| **XML-RPC** | Database Name, Username, Password / API Key \-\> uid | 100% via execute\_kw | Highly verbose XML payloads. Binary fields require Base64 encoding. Relational queries return shallow \[id, name\] arrays, causing N+1 query inefficiencies. Fully backward compatible but deprecated in Odoo 19 and scheduled for total removal in Odoo 22\. |
| **JSON-RPC (Legacy)** | Session Cookies or Token | 100% via execute\_kw | Utilized natively by the Odoo web client. Provides more efficient JSON payload parsing but suffers from a lack of formal documentation for external integrations. Scheduled for removal alongside XML-RPC in Odoo 22\. |
| **JSON-2 (REST)** | Bearer Token (API Key) | 100% via URL routing | Introduced in Odoo 19\. Routes directly to /json/2/\<model\>/\<method\>. Utilizes standard HTTP status codes for robust error handling. Requires Odoo 19+ and eliminates the need for the execute\_kw wrapper. |
| **Custom REST API** | OAuth2 / API Keys | Varies by module | Requires installation of third-party modules (e.g., OCA REST framework). Highly customized but fundamentally incompatible with Odoo.com SaaS environments due to strict restrictions on custom module installations. |
| **OData / GraphQL** | API Keys | Varies by module | Not supported natively. Achieved via community modules (e.g., graphql\_base by OCA) or external middleware (CData). Ideal for resolving deep relational graph queries but requires self-hosted or Odoo.sh deployment tiers. |

## **Detailed Findings**

### **SECTION 1: Odoo API Surface**

The programmatic interaction layer of Odoo provides extensive, unmitigated access to the underlying business logic and database schema, essentially exposing the entire ORM to external applications. However, the exact methods, endpoints, and authentication flows vary significantly depending on the version of Odoo deployed and the specific hosting environment.

#### **1.1 XML-RPC API**

The XML-RPC API has served as the foundational integration protocol for Odoo since version 6 and remains the most heavily documented interface for external systems.1 It operates entirely over HTTP POST requests utilizing XML payloads. The integration architecture relies on two distinct endpoints: /xmlrpc/2/common and /xmlrpc/2/object.3 The authentication flow dictates that the external application must first interface with the common endpoint, calling the authenticate method while passing the target database name, the username, and the user's password or API key.5 A successful authentication request does not return a continuous session token; rather, it returns an integer representing the User ID (uid).5 This uid must be cached by the integrating platform and passed alongside the password/API key in every subsequent data operation.6

All CRUD operations and custom method invocations are routed through the /xmlrpc/2/object endpoint utilizing a unified wrapper function known as execute\_kw (execute with keyword arguments).2 The structure of an execute\_kw call requires the database name, the uid, the authentication credential, the technical name of the target model (e.g., sale.order), the specific ORM method to invoke, a list of positional arguments, and a dictionary of keyword arguments (kwargs).6

The primary ORM methods exposed for external manipulation include search (which returns only an array of matching record IDs), read (which takes an array of IDs and returns the field data), search\_read (which combines the two operations for efficiency), create, write (update), and unlink (delete).1 When querying the database, the API utilizes a unique syntax for domain filters based on Polish notation (prefix notation).1 For example, to search for active customers in the United States or Canada, the domain array must precede the logical OR operator (|), structured as \`\`.1

The kwargs dictionary provides critical control over the returned data volume. Integrators can specify the fields array to limit the payload to explicitly required columns, avoiding the expensive retrieval of the entire record.1 Pagination is managed via the limit and offset arguments, while sorting is handled by the order argument.7

XML-RPC presents several profound limitations for autonomous AI agents. First, the search\_read method imposes a strict default batch size cap, returning a maximum of 100 records per call to prevent server memory exhaustion.9 While this can be overridden by explicitly declaring a higher limit, retrieving massive datasets requires the orchestrator to implement cursor-based pagination using the offset parameter.9 Second, binary fields (such as product images or document attachments) are transmitted as Base64-encoded strings.3 This drastically inflates the XML payload size, leading to severe latency and potential timeouts when agents process visual data. Most critically, the XML-RPC protocol struggles with relational field depth. When an agent queries a Many2one field (such as the partner\_id on a sales order), the API does not return the nested customer object. Instead, it returns a shallow tuple containing only the related record's ID and its display name, formatted as \[id, display\_name\].1 If the agent requires deeper information about that customer—such as their email or shipping address—it must execute a secondary read call against the res.partner model using that ID, creating a highly inefficient N+1 query problem that the orchestration layer must actively manage.1

Rate limiting adds another layer of complexity. On Odoo.com SaaS environments, external RPC calls are actively throttled. Sustained usage exceeding approximately one call per second can trigger temporary blocks or degraded performance.11 Consequently, agents must rely on batched operations rather than sequential single-record updates to maintain stability.11 Furthermore, Odoo has officially deprecated the /xmlrpc/2 endpoints as of version 19, scheduling them for complete removal in Odoo 22 (Fall 2028), mandating that long-term integration strategies pivot toward newer protocols.3

#### **1.2 JSON-RPC API**

Odoo exposes a secondary legacy protocol via the /jsonrpc endpoint.3 From an architectural standpoint, the JSON-RPC interface provides the exact same ORM capabilities and coverage as XML-RPC, routing calls through the same execute\_kw methodology.1 The primary distinction lies in the transport format; exchanging lightweight JSON objects rather than verbose XML tags significantly reduces bandwidth consumption and accelerates payload parsing times, particularly beneficial for JavaScript-based client applications.1

The Odoo web client relies heavily on this protocol internally, utilizing session cookies rather than the stateless uid/API key pairing required by the external XML-RPC flow.1 However, formal documentation detailing how external applications should construct JSON-RPC payloads is notoriously sparse, leading the broader development community to default to XML-RPC despite its performance drawbacks.1 Attempting to adapt the session-based browser calls for stateless external server-to-server integration often results in Cross-Site Request Forgery (CSRF) token errors and session expiration issues.15 Like its XML counterpart, the JSON-RPC interface is deprecated in version 19 and will be eliminated in version 22\.3

#### **1.3 REST API (Odoo 17+ & JSON-2)**

Historically, Odoo resisted implementing a native REST API, arguing that standard REST constraints failed to accurately map to the complex business logic and state-mutating actions inherent in an ERP's ORM.16 Odoo 16 and 17 introduced partial native REST interfaces, but coverage remained highly fragmented; core operational models such as HR, payroll, and complex accounting transactions were excluded, forcing integrators to continue relying on RPC.10

This architectural deficit was resolved in Odoo 19 with the introduction of the External JSON-2 API.3 The JSON-2 interface represents a complete modernization of Odoo's programmatic surface. It deprecates the generic /xmlrpc/2/object endpoint and the execute\_kw wrapper, replacing them with direct, model-specific routing structured as /json/2/\<model\>/\<method\>.4 Authentication has been entirely overhauled; the cumbersome process of passing a database, username, and password to retrieve a uid is replaced by standard HTTP Authorization: Bearer \<API\_KEY\> headers.4 Furthermore, if the deployment handles multiple tenants, the target database is specified cleanly via an X-Odoo-Database header.4

The JSON-2 payload mechanics resolve the positional argument complexities of XML-RPC. In JSON-2, all method arguments are passed as explicitly named parameters within the JSON body, alongside an ids array for the target records and an optional context object to dictate localization or timezone behaviors.4 Crucially for autonomous agents, JSON-2 abandons the legacy behavior of returning HTTP 200 OK codes for failed operations. Instead, it utilizes standard HTTP 4xx and 5xx status codes, accompanied by a serialized JSON error object detailing the Python exception name, a human-readable message, and the specific traceback, allowing an AI orchestration engine to parse the failure accurately and implement automated retry or self-correction logic.4

#### **1.4 OData / GraphQL**

Odoo does not natively expose OData or GraphQL endpoints in any version, including Odoo 19\.17 Given the inherent relational depth limitations of XML-RPC—where retrieving nested foreign key data requires multiple sequential network calls—GraphQL's ability to fetch deep, customized object graphs in a single request is highly desirable for AI data ingestion.

To achieve this capability, the ecosystem relies heavily on community-maintained extensions. The most prominent solution is the graphql\_base module developed by the Odoo Community Association (OCA).17 This module allows developers to define complex schemas using the Python graphene library, exposing a /graphql endpoint that natively respects Odoo's underlying access rights and record rules.17 An alternative approach involves deploying external middleware, such as the CData API Server, which wraps the Odoo PostgreSQL instance and dynamically generates compliant OData endpoints that support advanced $select, $filter, and $expand query parameters.18

The critical limitation of both GraphQL and OData solutions is their reliance on third-party application installations. Because Odoo.com SaaS environments strictly prohibit the installation of custom or community modules not explicitly certified by Odoo SA, these advanced query interfaces are completely unavailable to SaaS customers, restricting their usage exclusively to Odoo.sh and self-hosted on-premise deployments.21

#### **1.5 External API Authentication Options**

Authentication strategies must navigate both protocol requirements and strict commercial licensing gates. Since Odoo 14, the platform has supported the generation of persistent API keys as the primary mechanism for external authentication.2 Administrators generate these 160-bit secure keys via the User Preferences interface under Account Security.2 Once generated, the key is permanently obfuscated in the UI, requiring secure vaulting by the integrating platform.2 API keys operate as direct password substitutes in XML-RPC calls and as Bearer tokens in the newer JSON-2 API.4 The permissions granted to an API key are intrinsically linked to the underlying user account; therefore, standard security doctrine dictates the creation of a dedicated "Bot User" with precisely scoped access rights, rather than attaching external keys to highly privileged administrator accounts.4

Session cookie authentication is technically feasible but highly volatile, as it mimics browser behavior and is susceptible to sudden expiration and CSRF validation failures during server-to-server communication.15 Native OAuth2 support for external API ingestion does not exist out of the box, though it can be implemented via community modules such as api\_auth\_oauth2 on unrestricted hosting tiers.25 Multi-factor authentication (MFA) complicates credential-based logins but is seamlessly bypassed by API keys, further cementing them as the mandatory standard for autonomous integrations.

The most severe constraint regarding authentication is imposed by Odoo's commercial hosting model. Odoo.com SaaS customers operating on the "One App Free" or "Standard" pricing plans are completely blocked from accessing the external API.2 The interface for generating API keys is suppressed, and programmatic network requests to the RPC or JSON-2 endpoints are rejected at the infrastructure level.2 To enable external AI automation, SaaS customers must be upgraded to the "Custom" enterprise plan, which unlocks API functionality alongside multi-company management and the Odoo Studio customization suite.26 This commercial restriction must be explicitly handled by the agent platform's onboarding flow to prevent authentication failures.

### **SECTION 2: Odoo Data Model & Schema Discovery**

For an AI agent to reliably query records, execute transactions, and synthesize cross-departmental insights, it must possess a rigorous understanding of Odoo's underlying ORM architecture. Odoo operates on a heavily normalized PostgreSQL database abstracted by Python models.

#### **2.1 Core Data Models**

Odoo utilizes technical model names formatted via dot notation to represent specific business objects. The agent platform's internal knowledge base must map natural language intents to the following critical models across various functional domains:

* **Customer Relationship Management (CRM):** The crm.lead model acts as the central repository for both unqualified leads and mature opportunities.28 The progression of a deal is tracked via relationships to the crm.stage model.  
* **Sales & Quoting:** The sale.order model represents the header data for quotations and confirmed sales, while the associated sale.order.line model contains the specific products, quantities, and unit prices for that transaction.10  
* **Invoicing & Financial Accounting:** Odoo unified its accounting architecture to rely heavily on the account.move model, which singularly represents customer invoices, vendor bills, and internal journal entries based on its internal state.10 Payments processed against these moves are tracked in the account.payment model.  
* **Inventory & Logistics:** The stock.picking model governs distinct logistical operations, including receiving goods, internal warehouse transfers, and outbound delivery orders.10 The granular movement of items is logged in stock.move, while the absolute, real-time calculation of available inventory at a specific location is tracked within the stock.quant model.10  
* **Purchasing:** The purchase.order model dictates procurement actions from suppliers, supported by purchase.order.line items.  
* **Directory & Contacts:** The res.partner model is arguably the most referenced table in the database. It represents individual consumers, B2B customer accounts, supplier entities, and internal company addresses simultaneously, differentiated by boolean flags.1  
* **Human Resources:** Employee profiles are maintained in hr.employee. Requests for vacation or sick time interact with the hr.leave model.29  
* **Project Management:** High-level project parameters exist within project.project, while the granular, assignable units of work reside in project.task.29  
* **Customer Support (Helpdesk):** Ticketing operations are managed via the helpdesk.ticket model.30 Crucially, the entire Helpdesk module is exclusive to the proprietary Odoo Enterprise edition and does not exist in the open-source Community edition, meaning agents targeting self-hosted Community databases will fail if they attempt to invoke this model.31

#### **2.2 Schema Introspection**

An advanced agentic architecture should not rely on hardcoded, static maps of the Odoo schema, as versions change and administrators frequently implement deep database customizations. Instead, the agent can dynamically discover the exact topology of the database at runtime utilizing Odoo's built-in meta-models: ir.model and ir.model.fields.2

To ascertain which models are currently installed and active, the agent executes a standard search\_read API call against the ir.model object.2 This query returns a list of dictionaries containing the model parameter (the exact technical string, such as account.move) and a human-readable name (e.g., "Journal Entry").2

Once a target model is identified, the agent must determine its specific column structure. This is accomplished by invoking the rare but exceptionally powerful fields\_get ORM method against the target model (e.g., models.execute\_kw(db, uid, password, 'res.partner', 'fields\_get',, {})).34 The fields\_get response is a comprehensive metadata dictionary detailing every attribute of every field on that model.34 It reveals the technical field name, the data type (ttype, such as char, integer, boolean, or datetime), the UI string label, instructional help text, and whether the field is required or readonly at the database level.34

Crucially, fields\_get allows the agent to self-discover the relational graph. For foreign keys, the metadata dictionary explicitly defines the target model within the relation attribute, and for reverse lookups (One2many), it defines the relation\_field attribute.34 Furthermore, if a field is a dropdown menu (selection type), the fields\_get response provides the exact array of allowable tuple options, ensuring the agent never attempts to inject an invalid string into a restricted column.34 By caching the output of fields\_get, the AI platform can construct a flawless, database-specific context window for the LLM to write precise search domains and payload schemas.

#### **2.3 Custom Fields & Models**

Odoo permits extensive structural customization without direct code modifications via the Odoo Studio application, allowing business analysts to append custom fields to standard models or generate entirely new relational tables. The introspection API handles these customizations seamlessly. Odoo enforces a strict naming convention: any custom field or model generated dynamically must be prefixed with x\_.2 Often, fields generated specifically via the Studio UI receive an x\_studio\_ prefix.2

Because these custom entities are registered within the exact same ir.model and ir.model.fields meta-models as the core open-source framework, they are instantly accessible via the XML-RPC and JSON-2 APIs.2 An agent calling fields\_get will retrieve the metadata for x\_studio\_customer\_loyalty\_tier just as it would for the native email field. This guarantees that the agent can interact with heavily bespoke ERP deployments without requiring manual code adjustments on the integration platform.

### **SECTION 3: Real-Time Triggers & Events**

A reactive, agentic workflow requires the ability to receive real-time notifications when state changes occur within the ERP system, such as immediately initiating a triage sequence when a high-priority helpdesk.ticket is generated.

#### **3.1 Native Webhook / Event System**

Historically, Odoo lacked a native mechanism for pushing outbound events, forcing integrators to rely on polling. However, starting prominently in Odoo 17, a comprehensive native webhook system was integrated directly into the base.automation (Automated Actions) application.36 This architecture allows the database to dispatch HTTP POST requests to external URLs completely independent of custom module installations, making it fully viable for heavily restricted Odoo.com SaaS deployments.36

The trigger conditions available within base.automation are exceptionally granular. System administrators can configure automations to fire "On Creation" of a new record, "On Update" (with the ability to isolate specific trigger fields, ensuring the automation only fires if the stage\_id changes, rather than firing on every minor save), "On Deletion", or "Based on Timed Condition" (e.g., executing an action 48 hours after a lead enters a specific pipeline stage).38

When the action type is set to the default "Send Webhook Notification", Odoo generates a basic JSON payload that pushes the \_model name and the \_id of the modified record to the external listener.36 While useful, this simplistic payload forces the external agent platform to immediately execute a synchronous read call back to Odoo to fetch the actual record data, effectively doubling the network traffic and increasing latency.

To circumvent this inefficiency, the platform should leverage the "Execute Code" action type within base.automation. This powerful feature exposes a sandboxed Python execution environment directly within the Odoo UI.36 Within this environment, the script has access to the env (environment) and record objects.39 An integration engineer can write a custom Python script that utilizes the Odoo ORM to traverse relational fields, extract exactly the data required, format it into a complex, deeply nested JSON payload, and dispatch it synchronously using the Python requests library to the AI platform's webhook receiver.36 This approach ensures the agent receives maximum context with zero subsequent API latency. However, because the Python execution occurs synchronously on the Odoo worker thread, poorly optimized HTTP requests in the webhook script can cause performance degradation or timeouts in the Odoo user interface.

#### **3.2 Mail/Messaging Integration**

Odoo manages its internal communication, including the Chatter interface on records and the Discuss application, via models such as mail.message and mail.channel. Real-time delivery of these messages to the browser relies on a websocket-like architecture powered by the bus.bus longpolling mechanism.40

While it is theoretically possible to utilize this longpolling architecture for external integration by forcing an external system to maintain a persistent connection to the /longpolling/poll endpoint, the technical reality is severely prohibitive.41 In production environments, Odoo longpolling requires specific, complex configurations involving multiprocess worker scaling, SSL termination, and specialized reverse proxy routing (via NGINX or Apache) to prevent thread exhaustion.43 Furthermore, external systems attempting to consume this stream often face connection refused errors and broken pipes.42 Due to its architectural brittleness and the heavy infrastructure demands it places on the client, bus.bus longpolling is not a viable strategy for scalable, third-party agent integration.

#### **3.3 Polling-Based Approaches**

In scenarios where internal IT security policies explicitly block outbound webhooks, the AI platform must rely on persistent polling to detect state changes. The most efficient methodology for polling Odoo involves executing standard search\_read API queries heavily restricted by domain filters targeting the write\_date field.45 The write\_date field is an absolute timestamp reflecting the last user or system modification to a record.45 By storing the timestamp of the last successful poll, the platform can request only records modified after that exact microsecond. Integrators must avoid utilizing the \_\_last\_update field, as it is merely a concurrency helper mechanism that updates only during module upgrades and is not actually stored persistently in the database, rendering it useless for data synchronization.45

Given the explicit rate limitations on Odoo.com SaaS deployments (restricting external access to roughly one call per second), aggressive high-frequency polling is impossible without triggering temporary IP bans or severe throttling.11 Therefore, polling intervals must be intelligently batched. A recommended architecture would implement a dynamic decay strategy: polling critical models like sale.order every 1 to 5 minutes during business hours, and decaying to 30-minute intervals during periods of low activity, ensuring the system respects the infrastructural constraints of the SaaS tier.

#### **3.4 Custom Module Approach and Database Triggers**

For environments that permit deep architectural modifications—specifically Odoo.sh (Platform as a Service) and on-premise, self-hosted deployments—the installation of a custom, lightweight Python module provides the most resilient and scalable event architecture.21 A custom integration module can utilize standard Python decorators to override core ORM methods such as @api.model\_create\_multi, write, and unlink. When these methods are invoked anywhere in the system, the custom code can asynchronously place an event notification into a dedicated message queue (like RabbitMQ or Redis) or dispatch an optimized HTTP POST payload to the agent platform. This completely abstracts the webhook logic away from the fragile UI configurations of base.automation.

Furthermore, for exclusively self-hosted environments backed directly by PostgreSQL, administrators can implement native database-level triggers utilizing the LISTEN/NOTIFY protocols. This allows the database to stream changes directly from the Write-Ahead Log (WAL) to an external listener, guaranteeing microsecond latency. However, this approach bypasses the Odoo ORM entirely, meaning it circumvents all application-level security, access rights, and computed field logic, making it highly impractical and dangerous for standard integrations.

Crucially, the custom module and database trigger approaches are explicitly impossible on Odoo.com SaaS deployments. SaaS customers operate in a locked-down, multi-tenant environment and are strictly prohibited from installing third-party Python code or accessing the database layer.21 Therefore, any integration built for the SaaS tier must rely entirely on the native API and base.automation webhooks.

### **SECTION 4: Existing Ecosystem — What Already Exists**

#### **4.1 MCP Servers for Odoo**

The adoption of the Model Context Protocol (MCP) to standardize AI interactions with Odoo is currently in an early, open-source stage, with several implementations available on GitHub.

* **ivnvxd/mcp-server-odoo:** This is currently the most mature and widely referenced implementation.48 It provides comprehensive tools for searching, retrieving, creating, updating, and deleting records via natural language.48 A standout feature is its "smart field selection," which analyzes the target model and automatically truncates verbose payloads to preserve the LLM's token context limits.48 It also features a "YOLO mode," allowing the MCP server to connect to vanilla Odoo instances via standard XML-RPC without requiring the administrator to install a companion MCP module inside Odoo, significantly reducing deployment friction.48  
* **hachecito/odoo-mcp-improved:** Built as an expansive fork of the ivnvxd project, this implementation adds highly specific endpoints and tools tailored for complex supply chain operations, including Manufacturing (MRP) capacity monitoring, Bill of Materials (BOM) management, and deep purchase analytics.49  
* **CData MCP Server:** CData, a major enterprise data connectivity provider, offers a specialized MCP server.51 However, rather than utilizing Odoo's native ORM APIs, this server wraps CData's proprietary JDBC driver, effectively exposing Odoo's data to the LLM as relational SQL tables.51 While powerful for data analysts, this approach bypasses Odoo's application-level business logic and is generally restricted to read-only queries in its public implementation.51

#### **4.2 Official & Popular Odoo Libraries**

For platforms utilizing Python, the built-in xmlrpc.client library remains the ubiquitous standard for integration, requiring zero external dependencies and functioning reliably across legacy systems.1 However, for developers prioritizing performance, the odoo\_rpc package is the preferred choice for implementing JSON-RPC communication, featuring automatic session cookie management and superior error handling.12 In the JavaScript/Node.js ecosystem, the landscape is surprisingly barren. There is no official, actively maintained external SDK provided by Odoo SA. Developers building Node.js integrations generally rely on raw fetch or axios POST requests, manually formatting the stringent JSON-RPC or JSON-2 payload structures.1

#### **4.3 Integration Platforms (iPaaS)**

A review of the leading iPaaS providers highlights the complexities of integrating with Odoo's evolving API.

* **Zapier:** Zapier provides an extensive library of automated triggers and actions.53 It relies heavily on utilizing Odoo's base.automation to push outbound webhooks into Zapier's "Catch Hook" endpoints to achieve real-time triggers, while utilizing standard XML-RPC for outbound actions like creating a new Lead.28  
* **Make.com (Integromat):** Make requires the generation of standard API keys and connects predominantly via the XML-RPC interface.55 It provides dozens of pre-built modules for standard CRUD operations but is constrained by the same relational depth limitations inherent in the XML protocol.56  
* **n8n:** The n8n platform serves as a cautionary tale regarding Odoo's protocol shift. The native, built-in Odoo node in n8n was constructed exclusively around the legacy XML-RPC architecture.15 As users upgrade to newer Odoo versions or attempt to leverage the JSON-2 endpoints, the native node frequently fails due to authentication mismatches and deprecated endpoint routing.15 Consequently, enterprise n8n users are actively forced to abandon the native integration and construct raw HTTP Request nodes manually formatting XML or JSON payloads.58  
* **Workato:** Aimed at the enterprise tier, Workato provides pre-built custom connectors that support robust authentication and abstract the complexity of execute\_kw into simple "Upsert Record" or "Search Records" actions, relying heavily on standard API key deployments.59

#### **4.4 Odoo API Gateway capabilities**

Odoo does not produce a standalone, official API Gateway product or middleware server. All external API routing is handled internally by the core Python http.Controller framework (based on Werkzeug) that powers the web client.61 Organizations requiring advanced API traffic management, deep throttling limits, or WAF protections must deploy standard enterprise solutions (like Kong or AWS API Gateway) as reverse proxies in front of the Odoo instance.

### **SECTION 5: Practical Agent Use Cases & Standard Agents**

Given the precise technical realities of Odoo's schema introspection and API capabilities, the platform should deploy a suite of highly specialized, domain-specific AI agents. By segmenting capabilities, the platform can aggressively prune the schema context provided to the LLM, dramatically reducing token consumption and hallucination rates.

**1\. The CRM & Pipeline Agent**

* **Purpose:** Lead qualification, automated pipeline progression, and sales activity summarization.  
* **Target Models:** crm.lead, crm.stage, mail.message.  
* **API Methods:** search\_read to evaluate current lead status; write to update the stage\_id or user\_id; create to inject new records into the mail.message chatter for internal visibility.  
* **Triggers:** Real-time webhook invoked upon crm.lead creation via website form submission.  
* **Interaction Example:** *"Review the new inbound lead from Acme Corp. If the stated budget exceeds $50k, move the stage to 'Qualified' and assign it to Sarah."*  
* **Required Permissions:** Sales / User: All Documents.

**2\. The Sales Order & Quoting Agent**

* **Purpose:** Drafting rapid quotations, validating stock availability, and processing order confirmations.  
* **Target Models:** sale.order, sale.order.line, product.product.  
* **API Methods:** create utilizing the complex (0, 0, {values}) command protocol to generate the header and multiple line items in a single XML-RPC transaction; execute to trigger the action\_confirm state change method.  
* **Triggers:** Chat invocation by sales representatives or webhooks firing when a CRM opportunity is marked 'Won'.  
* **Interaction Example:** *"Draft a quote for 50 units of the Acoustic Desk Screen for Wayne Enterprises. Apply the standard 10% B2B discount."*  
* **Required Permissions:** Sales / User: All Documents.

**3\. The Invoicing & Dunning Agent**

* **Purpose:** Automated invoice generation, tracking of outstanding balances, and issuing payment reminders.  
* **Target Models:** account.move, account.payment.  
* **API Methods:** search\_read filtered by \[('payment\_state', '=', 'not\_paid'), ('move\_type', '=', 'out\_invoice')\].  
* **Triggers:** Scheduled polling sequence or a webhook triggered by a stock.picking delivery confirmation.  
* **Interaction Example:** *"List all unpaid invoices older than 45 days. Draft a polite follow-up email to each primary contact."*  
* **Required Permissions:** Accounting / Invoicing.

**4\. The Logistics & Inventory Agent**

* **Purpose:** Real-time stock level verification, tracking internal warehouse transfers, and managing delivery orders.  
* **Target Models:** stock.picking, stock.move, stock.quant.  
* **API Methods:** search\_read against stock.quant to determine absolute available quantities across different location\_id parameters.  
* **Triggers:** Chat invocation by customer service representatives.  
* **Interaction Example:** *"Do we have enough components in the Dallas warehouse to fulfill a sudden order of 500 widgets?"*  
* **Required Permissions:** Inventory / User.

**5\. The HR & Employee Self-Service Agent**

* **Purpose:** Handling leave requests, querying the internal directory, and summarizing attendance.  
* **Target Models:** hr.employee, hr.leave, hr.department.  
* **API Methods:** search\_read to check remaining leave allocation balances; create to draft an hr.leave request.  
* **Triggers:** Chat invocation via Slack/Teams integration.  
* **Interaction Example:** *"How many days of PTO do I have left? If it's more than three, request next Thursday and Friday off."*  
* **Required Permissions:** Human Resources / Officer.

**6\. The Enterprise Helpdesk Agent**

* **Purpose:** Automated ticket triaging, sentiment analysis, assignment, and resolution summarization.  
* **Target Models:** helpdesk.ticket. *(Note: The agent orchestration engine must gracefully fail or disable this agent if the target database is Odoo Community edition, as this model does not exist).*  
* **API Methods:** search\_read for open queues; write to update priority and SLA status.  
* **Triggers:** Webhook invoked on helpdesk.ticket creation.  
* **Interaction Example:** *"Summarize the last 5 updates on ticket \#4402 and escalate the priority to High."*  
* **Required Permissions:** Helpdesk / User.

**7\. The Schema Admin Agent**

* **Purpose:** Autonomous verification of user access rights and deep database schema introspection.  
* **Target Models:** res.users, ir.model, ir.model.fields.  
* **API Methods:** Regular execution of fields\_get to update the LLM's understanding of the relational database map.  
* **Triggers:** System-level CRON or manual invocation by the integration engineer.  
* **Interaction Example:** *"Did the client add any custom fields to the Contact model yesterday? Map them to our internal data standard."*  
* **Required Permissions:** Administration / Settings.

### **SECTION 6: Architecture Decision Record (ADR)**

The transition from XML-RPC to JSON-2, combined with the stringent API restrictions of the SaaS Standard tier, mandates a highly resilient, multi-layered architectural approach to ensure platform stability.

#### **6.1 Connection & Protocol Strategy**

The platform must implement a dynamic, protocol-agnostic connection negotiator.

* **Protocol Routing:** For legacy environments (Odoo 15 through 18), the connection manager should prioritize JSON-RPC over XML-RPC to minimize payload bloat and accelerate parsing, falling back to XML-RPC only if specific structural anomalies arise. For Odoo 19+ instances, the system must definitively upgrade to the JSON-2 API, abandoning execute\_kw in favor of direct endpoint routing.  
* **Authentication:** The platform will strictly mandate the use of API Keys for all connections, vaulting them with AES-256 encryption. Session cookie authentication is explicitly forbidden due to volatility.  
* **SaaS Gating:** The onboarding UI must explicitly verify the customer's hosting tier. If a customer attempts to authenticate an Odoo.com SaaS "Standard" or "One App Free" database, the platform must clearly display an error indicating that Odoo blocks API access on these tiers, instructing them to upgrade to the "Custom" plan.

#### **6.2 Event & Trigger Strategy**

The event strategy must be tiered based on the permissibility of the hosting deployment:

1. **Primary Strategy (SaaS Custom / General Webhooks):** Utilize Odoo's native base.automation webhooks. To mitigate the latency of secondary API read calls, the agent platform should generate an optimized Python code snippet during onboarding. The customer pastes this script into the "Execute Code" action in Odoo Studio. This script traverses the necessary relational fields and pushes a fully hydrated, flat JSON payload to the platform's webhook receiver.  
2. **Optimized Strategy (Odoo.sh / Self-Hosted):** For environments permitting code modifications, the platform will offer an installable Odoo module (x\_agent\_integration). This module intercepts @api.model\_create\_multi and write calls at the ORM level, asynchronously dispatching highly structured events to the platform without requiring fragile UI configuration by the user.  
3. **Fallback Strategy (Polling):** For environments where strict internal firewalls block outbound webhooks, the platform implements an adaptive polling microservice. The service executes search\_read queries heavily filtered by \[('write\_date', '\>', last\_poll\_timestamp)\]. To respect the 1 call/second SaaS rate limit, the polling frequency will utilize a dynamic decay algorithm, executing every 60 seconds during high-volume business hours and backing off to 15-minute intervals during stagnation.

#### **6.3 Schema Caching Strategy**

Dynamic introspection is vital to prevent LLM hallucinations. Upon initial authentication, the Schema Admin Agent initiates a background job querying ir.model and calling fields\_get on all discovered models. This rich metadata dictionary—detailing field types, relationships, and selection arrays—is cached locally within the platform's Redis or SQLite infrastructure. Because businesses continually modify their ERP via Odoo Studio (creating x\_studio\_ fields), the platform schedules a nightly introspection refresh. When the LLM generates an API payload, it validates the structure against this local cache, ensuring absolute compliance with Odoo's strict relational constraints.

#### **6.4 Security & Multi-Tenancy Model**

Security dictates absolute adherence to the principle of least privilege. The platform onboarding documentation will mandate that customers create a dedicated "Agent Bot" user within Odoo (e.g., AI\_Orchestrator\_Bot), granting it only the specific application rights required by the enabled agents. The platform will refuse API keys generated by the primary Administrator account. To accommodate massive enterprise structures, the platform will support Odoo's native multi-company architecture. Users can map specific agents to specific Odoo company\_id records, ensuring the agent only acts within the designated corporate boundary by passing the appropriate context dictionary in the API headers.

#### **6.5 Build Backlog**

Based on the architectural findings, the following core components must be prioritized for immediate engineering:

| Priority | Component | Description | Est. Complexity |
| :---- | :---- | :---- | :---- |
| **1** | **Auth & Protocol Router** | Service that dynamically negotiates between JSON-RPC (v15-18) and JSON-2 (v19+), manages AES-256 encrypted API keys, and detects/rejects SaaS "Standard" plan databases. | **Large** |
| **2** | **Schema Introspection Engine** | Background worker orchestrating widespread fields\_get executions. Populates a local SQLite cache allowing the LLM to understand foreign keys and custom x\_ fields without latency. | **Medium** |
| **3** | **Webhook Code Generator** | A UI module that auto-generates optimized Python scripts for customers to paste into Odoo's base.automation, ensuring incoming payloads are flat, rich, and require zero secondary API reads. | **Small** |
| **4** | **Adaptive Polling Service** | A resilient fallback microservice utilizing write\_date filters, cursor-based pagination (limit/offset), and rate-limit backoff algorithms to safely ingest data when webhooks are blocked. | **Medium** |
| **5** | **Agent MCP Skill Files** | Construction of pre-defined system prompts mapping natural language intents to strict Odoo technical models via the Model Context Protocol, utilizing the insights from existing repos like ivnvxd/mcp-server-odoo. | **Medium** |

### **Open Questions for Hands-on Testing**

1. **JSON-2 Relational Latency:** While JSON-2 modernizes the payload and error handling structure, does it natively resolve the N+1 relational query latency observed in XML-RPC? Specifically, does querying a Many2one field in JSON-2 still require a subsequent API request to fetch the underlying relational data, or does it support automated graph expansion?  
2. **Webhook Python Execution Limits:** What is the absolute byte limit or execution timeout ceiling for the base.automation Python requests.post() script before the primary Odoo worker thread forcefully terminates the operation, potentially breaking the user interface?  
3. **SaaS Rate Limit Signatures:** Exactly how many sequential, paginated search\_read operations trigger the Odoo.com SaaS infrastructural throttling mechanisms, and what specific HTTP headers or error codes reliably indicate impending rate limits to trigger the platform's backoff algorithm?

#### **Works cited**

1. Odoo API Integration Guide — XML-RPC, JSON-RPC & REST (2026) \- OEC.sh, accessed March 24, 2026, [https://oec.sh/blog/odoo-api-integration](https://oec.sh/blog/odoo-api-integration)  
2. External API — Odoo 18.0 documentation, accessed March 24, 2026, [https://www.odoo.com/documentation/18.0/developer/reference/external\_api.html](https://www.odoo.com/documentation/18.0/developer/reference/external_api.html)  
3. External RPC API — Odoo 19.0 documentation, accessed March 24, 2026, [https://www.odoo.com/documentation/19.0/developer/reference/external\_rpc\_api.html](https://www.odoo.com/documentation/19.0/developer/reference/external_rpc_api.html)  
4. External JSON-2 API — Odoo 19.0 documentation, accessed March 24, 2026, [https://www.odoo.com/documentation/19.0/developer/reference/external\_api.html](https://www.odoo.com/documentation/19.0/developer/reference/external_api.html)  
5. External API — Odoo 17.0 documentation, accessed March 24, 2026, [https://www.odoo.com/documentation/17.0/developer/reference/external\_api.html](https://www.odoo.com/documentation/17.0/developer/reference/external_api.html)  
6. Web Service API — odoo 10.0 documentation, accessed March 24, 2026, [https://www.odoo.com/documentation/saas-13/api\_integration.html](https://www.odoo.com/documentation/saas-13/api_integration.html)  
7. How To Read Records | Odoo, accessed March 24, 2026, [https://www.odoo.com/forum/help-1/how-to-read-records-181957](https://www.odoo.com/forum/help-1/how-to-read-records-181957)  
8. JSON-RPC \- define request parameters like limit or fields \- Odoo, accessed March 24, 2026, [https://www.odoo.com/forum/help-1/json-rpc-define-request-parameters-like-limit-or-fields-164311](https://www.odoo.com/forum/help-1/json-rpc-define-request-parameters-like-limit-or-fields-164311)  
9. XML-RPC API search\_read method 100 records' limitation \- Odoo, accessed March 24, 2026, [https://www.odoo.com/forum/help-1/xml-rpc-api-search-read-method-100-records-limitation-216563](https://www.odoo.com/forum/help-1/xml-rpc-api-search-read-method-100-records-limitation-216563)  
10. Odoo API Integration Guide (In-Depth) \- Knit, accessed March 24, 2026, [https://www.getknit.dev/blog/odoo-api-integration-guide-in-depth](https://www.getknit.dev/blog/odoo-api-integration-guide-in-depth)  
11. Odoo Cloud \- Acceptable Use Policy, accessed March 24, 2026, [https://www.odoo.com/acceptable-use](https://www.odoo.com/acceptable-use)  
12. How Mobo Apps Communicate with Odoo (XML-RPC vs JSON-RPC), accessed March 24, 2026, [https://www.cybrosys.com/blog/how-mobo-apps-communicate-with-odoo-xml-rpc-vs-json-rpc](https://www.cybrosys.com/blog/how-mobo-apps-communicate-with-odoo-xml-rpc-vs-json-rpc)  
13. Question about how to authentication using api key \- Odoo, accessed March 24, 2026, [https://www.odoo.com/forum/help-1/question-about-how-to-authentication-using-api-key-275806](https://www.odoo.com/forum/help-1/question-about-how-to-authentication-using-api-key-275806)  
14. External API documentation (JSON-RPC) \- Odoo, accessed March 24, 2026, [https://www.odoo.com/forum/help-1/external-api-documentation-json-rpc-236874](https://www.odoo.com/forum/help-1/external-api-documentation-json-rpc-236874)  
15. Odoo Node outdated? \- Questions \- n8n Community, accessed March 24, 2026, [https://community.n8n.io/t/odoo-node-outdated/230171](https://community.n8n.io/t/odoo-node-outdated/230171)  
16. XMLRPC is dead. All Hail JSON-2. \- Oduist, accessed March 24, 2026, [https://oduist.com/blog/odoo-experience-2025-ai-summaries-2/286-xmlrpc-is-dead-all-hail-json-2-288](https://oduist.com/blog/odoo-experience-2025-ai-summaries-2/286-xmlrpc-is-dead-all-hail-json-2-288)  
17. Graphql Base | The Odoo Community Association | OCA, accessed March 24, 2026, [https://odoo-community.org/shop/graphql-base-4712](https://odoo-community.org/shop/graphql-base-4712)  
18. OData APIs for Odoo \- CData Software, accessed March 24, 2026, [https://www.cdata.com/drivers/odoo/odata/](https://www.cdata.com/drivers/odoo/odata/)  
19. Odoo GraphQL | Odoo Apps Store, accessed March 24, 2026, [https://apps.odoo.com/apps/modules/14.0/odoo\_graphql](https://apps.odoo.com/apps/modules/14.0/odoo_graphql)  
20. Automate Odoo Tasks in Power Automate Using CData API Server, accessed March 24, 2026, [https://www.cdata.com/kb/tech/odoo-odata-power-automate.rst](https://www.cdata.com/kb/tech/odoo-odata-power-automate.rst)  
21. Odoo Hosting Compared: SaaS, On-Premise & SH \- Ksolves, accessed March 24, 2026, [https://www.ksolves.com/blog/odoo/comparing-odoo-saas-odoo-on-premise-and-sh](https://www.ksolves.com/blog/odoo/comparing-odoo-saas-odoo-on-premise-and-sh)  
22. How to Choose Your Hosting Type \- Odoo, accessed March 24, 2026, [https://www.odoo.com/blog/business-hacks-1/how-to-choose-your-hosting-type-560](https://www.odoo.com/blog/business-hacks-1/how-to-choose-your-hosting-type-560)  
23. How to Seamlessly Connect Your Business Applications with Odoo API \- Cudio, accessed March 24, 2026, [https://www.cudio.com/odoo-api-integration-how-to-seamlessly-connect-your-business-applications](https://www.cudio.com/odoo-api-integration-how-to-seamlessly-connect-your-business-applications)  
24. Limiting API permissions : r/Odoo \- Reddit, accessed March 24, 2026, [https://www.reddit.com/r/Odoo/comments/1ph6zs9/limiting\_api\_permissions/](https://www.reddit.com/r/Odoo/comments/1ph6zs9/limiting_api_permissions/)  
25. API OAuth2 Authentication \- Odoo Apps Store, accessed March 24, 2026, [https://apps.odoo.com/apps/modules/17.0/api\_auth\_oauth2](https://apps.odoo.com/apps/modules/17.0/api_auth_oauth2)  
26. Odoo Pricing | Discover Odoo Plans, accessed March 24, 2026, [https://www.odoo.com/pricing](https://www.odoo.com/pricing)  
27. Odoo Customization vs. Standard: Which ERP Plan Suits Your Business? \- Cudio, accessed March 24, 2026, [https://www.cudio.com/blogs/odoo-customization-vs-standard](https://www.cudio.com/blogs/odoo-customization-vs-standard)  
28. Zapier and Odoo Self Hosting \- Reddit, accessed March 24, 2026, [https://www.reddit.com/r/Odoo/comments/14lrkka/zapier\_and\_odoo\_self\_hosting/](https://www.reddit.com/r/Odoo/comments/14lrkka/zapier_and_odoo_self_hosting/)  
29. Human resources — Odoo 19.0 documentation, accessed March 24, 2026, [https://www.odoo.com/documentation/19.0/applications/hr.html](https://www.odoo.com/documentation/19.0/applications/hr.html)  
30. Helpdesk — Odoo 19.0 documentation, accessed March 24, 2026, [https://www.odoo.com/documentation/19.0/applications/services/helpdesk.html](https://www.odoo.com/documentation/19.0/applications/services/helpdesk.html)  
31. Odoo Community vs Enterprise: Compare Plans & Choose Smart | Cybrosys, accessed March 24, 2026, [https://www.cybrosys.com/odoo/compare-odoo-community-vs-enterprise/](https://www.cybrosys.com/odoo/compare-odoo-community-vs-enterprise/)  
32. Odoo Enterprise vs Community | Odoo Editions Comparison, accessed March 24, 2026, [https://www.odoo.com/page/editions](https://www.odoo.com/page/editions)  
33. How to retrieve complete model schema via XML-RPC for documentation \- Odoo, accessed March 24, 2026, [https://www.odoo.com/forum/help-1/how-to-retrieve-complete-model-schema-via-xml-rpc-for-documentation-288086](https://www.odoo.com/forum/help-1/how-to-retrieve-complete-model-schema-via-xml-rpc-for-documentation-288086)  
34. Overview of fields\_get() in Odoo 19 \- Cybrosys Technologies, accessed March 24, 2026, [https://www.cybrosys.com/blog/overview-of-fieldsget-in-odoo-19](https://www.cybrosys.com/blog/overview-of-fieldsget-in-odoo-19)  
35. ir.model | Rest API \- GitBook, accessed March 24, 2026, [https://synconics.gitbook.io/rest-api/inspection-and-introspection/ir.model](https://synconics.gitbook.io/rest-api/inspection-and-introspection/ir.model)  
36. Webhooks — Odoo 19.0 documentation, accessed March 24, 2026, [https://www.odoo.com/documentation/19.0/applications/studio/automated\_actions/webhooks.html](https://www.odoo.com/documentation/19.0/applications/studio/automated_actions/webhooks.html)  
37. How to use Webhook with automated action in Odoo, accessed March 24, 2026, [https://www.odoo.com/forum/help-1/how-to-use-webhook-with-automated-action-in-odoo-238714](https://www.odoo.com/forum/help-1/how-to-use-webhook-with-automated-action-in-odoo-238714)  
38. Automated actions (automations) — Odoo 16.0 documentation, accessed March 24, 2026, [https://www.odoo.com/documentation/16.0/applications/studio/automated\_actions.html](https://www.odoo.com/documentation/16.0/applications/studio/automated_actions.html)  
39. Automation rules — Odoo 19.0 documentation, accessed March 24, 2026, [https://www.odoo.com/documentation/19.0/applications/studio/automated\_actions.html](https://www.odoo.com/documentation/19.0/applications/studio/automated_actions.html)  
40. odoo-development/docs/odoo/models/bus.bus.rst at master \- GitHub, accessed March 24, 2026, [https://github.com/itpp-labs/odoo-development/blob/master/docs/odoo/models/bus.bus.rst](https://github.com/itpp-labs/odoo-development/blob/master/docs/odoo/models/bus.bus.rst)  
41. How do i utilize odoo's websocket connection, accessed March 24, 2026, [https://www.odoo.com/forum/help-1/how-do-i-utilize-odoos-websocket-connection-284722](https://www.odoo.com/forum/help-1/how-do-i-utilize-odoos-websocket-connection-284722)  
42. Polling process can't connect to DB over a NGINX reverse proxy \- Odoo, accessed March 24, 2026, [https://www.odoo.com/forum/help-1/polling-process-cant-connect-to-db-over-a-nginx-reverse-proxy-189456](https://www.odoo.com/forum/help-1/polling-process-cant-connect-to-db-over-a-nginx-reverse-proxy-189456)  
43. How to use odoo longpolling without reverse proxy & domain name \- Stack Overflow, accessed March 24, 2026, [https://stackoverflow.com/questions/66212140/how-to-use-odoo-longpolling-without-reverse-proxy-domain-name](https://stackoverflow.com/questions/66212140/how-to-use-odoo-longpolling-without-reverse-proxy-domain-name)  
44. Odoo 14: longpolling bus.Bus unavailable running behind GKE Ingress, accessed March 24, 2026, [https://www.odoo.com/forum/help-1/odoo-14-longpolling-busbus-unavailable-running-behind-gke-ingress-190170](https://www.odoo.com/forum/help-1/odoo-14-longpolling-busbus-unavailable-running-behind-gke-ingress-190170)  
45. What is difference between \_\_last\_update and write\_date \- Odoo, accessed March 24, 2026, [https://www.odoo.com/forum/help-1/what-is-difference-between-last-update-and-write-date-199338](https://www.odoo.com/forum/help-1/what-is-difference-between-last-update-and-write-date-199338)  
46. What is difference between \_\_last\_update and write\_date \- Odoo, accessed March 24, 2026, [https://www.odoo.com/it\_IT/forum/assistenza-1/what-is-difference-between-last-update-and-write-date-199338/](https://www.odoo.com/it_IT/forum/assistenza-1/what-is-difference-between-last-update-and-write-date-199338/)  
47. Where's the line between Odoo SaaS customization and needing Odoo.sh? \- Reddit, accessed March 24, 2026, [https://www.reddit.com/r/Odoo/comments/1mozxd9/wheres\_the\_line\_between\_odoo\_saas\_customization/](https://www.reddit.com/r/Odoo/comments/1mozxd9/wheres_the_line_between_odoo_saas_customization/)  
48. A Model Context Protocol (MCP) server that enables AI assistants to securely interact with Odoo ERP systems through standardized resources and tools for data retrieval and manipulation. \- GitHub, accessed March 24, 2026, [https://github.com/ivnvxd/mcp-server-odoo](https://github.com/ivnvxd/mcp-server-odoo)  
49. hachecito/odoo-mcp-improved \- GitHub, accessed March 24, 2026, [https://github.com/hachecito/odoo-mcp-improved](https://github.com/hachecito/odoo-mcp-improved)  
50. Odoo MCP Server, accessed March 24, 2026, [https://mcpservers.org/servers/sarakhanx/odoo-mcp-server](https://mcpservers.org/servers/sarakhanx/odoo-mcp-server)  
51. odoo-mcp-server-by-cdata \- GitHub, accessed March 24, 2026, [https://github.com/CDataSoftware/odoo-mcp-server-by-cdata](https://github.com/CDataSoftware/odoo-mcp-server-by-cdata)  
52. Mastering the Odoo Python API as an Odoo Python Developer \- DEV Community, accessed March 24, 2026, [https://dev.to/webbycrownsolutions/mastering-the-odoo-python-api-as-an-odoo-python-developer-4nlo](https://dev.to/webbycrownsolutions/mastering-the-odoo-python-api-as-an-odoo-python-developer-4nlo)  
53. Odoo CRM Webhooks by Zapier Integration \- Quick Connect, accessed March 24, 2026, [https://zapier.com/apps/odoo/integrations/webhook](https://zapier.com/apps/odoo/integrations/webhook)  
54. Odoo CRM Salesforce Integration \- Quick Connect \- Zapier, accessed March 24, 2026, [https://zapier.com/apps/odoo/integrations/salesforce](https://zapier.com/apps/odoo/integrations/salesforce)  
55. Odoo \- Apps Documentation \- Make, accessed March 24, 2026, [https://apps.make.com/odoo](https://apps.make.com/odoo)  
56. Odoo Integration | Workflow Automation \- Make, accessed March 24, 2026, [https://www.make.com/en/integrations/odoo](https://www.make.com/en/integrations/odoo)  
57. Odoo Node still uses deprecated RPC endpoints (Odoo 19+) · Issue \#21545 · n8n-io/n8n, accessed March 24, 2026, [https://github.com/n8n-io/n8n/issues/21545](https://github.com/n8n-io/n8n/issues/21545)  
58. Post to an XMLRPC API via the HTTP Request node | n8n workflow template, accessed March 24, 2026, [https://n8n.io/workflows/2888-post-to-an-xmlrpc-api-via-the-http-request-node/](https://n8n.io/workflows/2888-post-to-an-xmlrpc-api-via-the-http-request-node/)  
59. Connectors | Workato Docs, accessed March 24, 2026, [https://docs.workato.com/connectors.html](https://docs.workato.com/connectors.html)  
60. Odoo and Workable integration | Workato, accessed March 24, 2026, [https://www.workato.com/integrations/odoo\~workable](https://www.workato.com/integrations/odoo~workable)  
61. Web Controllers — Odoo 19.0 documentation, accessed March 24, 2026, [https://www.odoo.com/documentation/19.0/developer/reference/backend/http.html](https://www.odoo.com/documentation/19.0/developer/reference/backend/http.html)  
62. Build REST API Endpoints in Odoo \- Braincuber Technologies, accessed March 24, 2026, [https://www.braincuber.com/tutorial/building-rest-api-endpoints-custom-odoo-modules](https://www.braincuber.com/tutorial/building-rest-api-endpoints-custom-odoo-modules)