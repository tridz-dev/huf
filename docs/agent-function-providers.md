# Agent Function Providers — `huf_agent_functions` Hook

## The Problem

The built-in `huf_tools` hook + `Agent Tool Function` DocType workflow works well for atomic Frappe operations (CRUD, report runs, single `get_value` calls). It falls short when you need a richer **domain function** that ties multiple Frappe calls together — for example:

- `get_customer_full_profile(customer_id)` → fetches the Customer doc, its open Sales Orders, linked Addresses, and Contact details in one shot
- `summarise_monthly_inventory(warehouse)` → runs two reports, merges results, formats a summary
- `search_knowledge_by_category(query, category)` → wraps the standard knowledge-search but pre-filters sources by metadata

These functions are awkward to express through the DocType-driven tool system: they don't map to a single DocType, they often need local Python logic, and storing them in the DB adds an unnecessary sync step.

---

## The Pattern: `huf_agent_functions` Hook

Any Frappe app can register **Python callables** directly against specific agents (or all agents) via a new hook:

```python
# myapp/hooks.py

huf_agent_functions = {
    # Agent name  →  list of dotted import paths to callables
    "Customer Support Agent": [
        "myapp.agent_functions.customer.get_customer_full_profile",
        "myapp.agent_functions.customer.escalate_ticket_with_history",
    ],
    "Inventory Agent": [
        "myapp.agent_functions.inventory.get_stock_summary",
        "myapp.agent_functions.inventory.reorder_suggestion",
    ],
    # Use "*" to expose a function to every agent
    "*": [
        "myapp.agent_functions.shared.lookup_user_by_email",
    ],
}
```

At runtime, `AgentManager._setup_tools()` imports each path, wraps it with `@function_tool`, and appends it to the agent's tool list — **no database sync required**.

---

## How to Write a Provider Function

### Requirements

| Requirement | Detail |
|-------------|--------|
| **Typed signature** | All parameters must have Python type annotations. The SDK uses these to generate the JSON schema shown to the LLM. |
| **Docstring** | Mandatory. The first line becomes the tool description the LLM sees. Use Google-style args docs for parameter descriptions. |
| **Return type** | Must be `str` or JSON-serialisable `dict` / `list`. Return `str` for free-form results; `dict` for structured data. |
| **No side effects on failure** | Return `{"success": False, "error": "..."}` instead of raising — lets the LLM report the issue gracefully. |
| **Frappe session context** | Functions run inside a normal Frappe request or background job, so `frappe.session.user`, `frappe.db`, etc. are all available. |

### Minimal Example

```python
# myapp/agent_functions/customer.py

import frappe
from frappe import client


def get_customer_full_profile(customer_id: str) -> dict:
    """Return a complete customer profile including open orders and addresses.

    Args:
        customer_id: The Customer document name (e.g. "CUST-00001")
    """
    if not frappe.db.exists("Customer", customer_id):
        return {"success": False, "error": f"Customer {customer_id!r} not found"}

    customer = client.get("Customer", customer_id)

    open_orders = frappe.get_list(
        "Sales Order",
        filters={"customer": customer_id, "status": ["in", ["Draft", "To Deliver and Bill"]]},
        fields=["name", "transaction_date", "grand_total", "status"],
        limit=20,
    )

    addresses = frappe.get_list(
        "Address",
        filters=[["Dynamic Link", "link_doctype", "=", "Customer"],
                 ["Dynamic Link", "link_name", "=", customer_id]],
        fields=["name", "address_type", "city", "country"],
    )

    return {
        "success": True,
        "customer": customer,
        "open_orders": open_orders,
        "addresses": addresses,
    }
```

### Knowledge Wrapper Example

Useful when you want to give an agent a knowledge-search tool that is **pre-scoped** to certain sources or categories:

```python
# myapp/agent_functions/hr_knowledge.py

import frappe


def search_hr_policies(query: str, category: str = None) -> str:
    """Search the HR knowledge base for policy information.

    Args:
        query: Natural language search query
        category: Optional policy category filter (e.g. "Leave", "Payroll")
    """
    from huf.ai.knowledge.retriever import KnowledgeRetriever

    retriever = KnowledgeRetriever(agent_name="HR Assistant Agent")
    results = retriever.search(query, top_k=5, metadata_filter={"category": category} if category else None)

    if not results:
        return "No relevant HR policy documents found."

    sections = []
    for r in results:
        sections.append(f"### {r['title']}\n{r['content']}")

    return "\n\n".join(sections)
```

---

## Registration in `hooks.py`

```python
# myapp/hooks.py

app_name = "myapp"
# ... other hooks ...

huf_agent_functions = {
    "HR Assistant Agent": [
        "myapp.agent_functions.hr_knowledge.search_hr_policies",
        "myapp.agent_functions.hr.get_employee_leave_balance",
    ],
    "Customer Support Agent": [
        "myapp.agent_functions.customer.get_customer_full_profile",
        "myapp.agent_functions.customer.escalate_ticket_with_history",
    ],
    # Shared across all agents
    "*": [
        "myapp.agent_functions.shared.get_current_fiscal_year",
    ],
}
```

---

## How It Works Internally

`AgentManager._setup_tools()` (in `huf/ai/agent_integration.py`) has three existing loading steps:

1. **DocType tools** — `Agent Tool Function` records linked to the agent (CRUD, HTTP, custom fn, etc.)
2. **Knowledge tools** — auto-injected if the agent has linked Knowledge Sources
3. **App-provided callables** ← *this is the new fourth step*

The loader (to be implemented in `agent_integration.py`):

```python
# Step 4 — huf_agent_functions hook
import importlib
from agents import function_tool

agent_name = self.agent_doc.agent_name

for hook_entry in frappe.get_hooks("huf_agent_functions") or []:
    # Each app contributes a dict {agent_name_or_"*": [paths]}
    for target, func_paths in hook_entry.items():
        if target not in (agent_name, "*"):
            continue
        for func_path in func_paths:
            try:
                module_path, fn_name = func_path.rsplit(".", 1)
                module = importlib.import_module(module_path)
                fn = getattr(module, fn_name)
                if callable(fn):
                    self.tools.append(function_tool(fn))
            except Exception as e:
                frappe.log_error(
                    f"Failed to load agent function {func_path!r}: {e}",
                    "Agent Function Provider Error",
                )
```

Key properties:
- **No sync step** — functions are imported fresh each request (module cache applies normally)
- **No DocType record** — nothing written to the DB; purely declarative
- **Fail-safe** — a bad import logs an error but doesn't crash the agent
- **Ordering** — DocType tools load first; app-provided functions are appended after

---

## `huf_agent_functions` vs `huf_tools` — When to Use Which

| Situation | Use |
|-----------|-----|
| Simple CRUD on a known DocType | `huf_tools` → `Agent Tool Function` |
| HTTP/webhook call | `huf_tools` → `Agent Tool Function` (type = `POST`/`GET`) |
| Logic spanning 2+ Frappe calls | `huf_agent_functions` |
| Domain function needing Python control flow | `huf_agent_functions` |
| Function scoped to **one** specific agent | `huf_agent_functions` (target by name) |
| Function needed by all agents | `huf_agent_functions` (target `"*"`) |
| Knowledge search with custom filters | `huf_agent_functions` (wrap `KnowledgeRetriever`) |
| Needs UI configuration by end users | `huf_tools` → `Agent Tool Function` (has DocType form) |

---

## Security Considerations

- Functions run with the **current `frappe.session.user`** context — normal Frappe permission checks (`frappe.has_permission`, `frappe.get_doc`) still apply.
- Do **not** bypass permissions inside provider functions (avoid `ignore_permissions=True` unless you perform your own explicit checks).
- Validate and sanitise all LLM-supplied arguments at the top of the function — treat them the same as user input.
- If a function can mutate data, consider calling `frappe.has_permission(doctype, "write")` before proceeding.
- Avoid exposing file system paths or internal configuration through tool return values.

---

## Future: Agent-Level Module Config

A complementary approach (suitable for per-site configuration rather than per-app) is to add a field to the `Agent` DocType:

```
agent_function_module  (Data field)
# e.g.  "myapp.agent_functions.customer"
```

`AgentManager` would then import that module and auto-discover all public callables (those not starting with `_`), wrapping each as a `function_tool`. This gives site administrators a way to attach custom logic without deploying a full app. The `huf_agent_functions` hook is the recommended approach for app developers; the module field is the escape hatch for site-level customisation.

---

## Summary

| | `huf_tools` hook | `huf_agent_functions` hook | Agent `function_module` field |
|---|---|---|---|
| Stored in DB | Yes (synced DocType) | No | No |
| UI configurable | Yes | No | Yes (field on Agent doc) |
| Complex Python logic | Limited | Yes | Yes |
| Agent-targeted | No (all agents) | Yes | Yes (per-agent) |
| Sync step needed | Yes (`after_migrate`) | No | No |
| Discovery | Automatic | Automatic | Manual (field must be set) |
