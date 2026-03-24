---
name: Odoo Integration
description: First-class integration for Odoo ERP into the HUF AI system, supporting multi-protocol RPC and event synchronization.
---

# Odoo Integration Skill

This skill provides the HUF AI agents with the ability to interact with Odoo ERP instances using a robust, protocol-agnostic RPC engine.

## Core Capabilities

1.  **Multi-Protocol RPC**: Supports XML-RPC (Odoo < 12), JSON-RPC (Odoo 12-18), and JSON-2 (Odoo 19+).
2.  **Schema Discovery**: Automatic introspection and caching of Odoo models and fields.
3.  **Hybrid Sync**: Real-time webhooks combined with an adaptive polling fallback.
4.  **Domain Awareness**: Pre-built logic for CRM (leads/partners), Sales (orders/invoices), and Inventory (stock/moves).

## Architecture & Patterns

### 1. Safe Invoke Pattern
All Odoo calls must use the `odoo_safe_invoke` decorator or follow its pattern to normalize Odoo's internal exceptions into AI-friendly messages.

```python
from huf.ai.odoo.tool_handlers import odoo_safe_invoke

@odoo_safe_invoke
def my_odoo_tool(model, **kwargs):
    # Logic here
    pass
```

### 2. O2M/M2M Command Array Pattern
When updating Odoo relational fields, use the standard command list format:
- `(0, 0, {values})`: Create new record
- `(1, id, {values})`: Update existing record
- `(2, id, 0)`: Delete/unlink record
- `(4, id, 0)`: Link existing record

### 3. Schema Discovery Pattern
To reduce latency and context window bloat, always check `Odoo Schema Cache` first before calling `fields_get`.

## Directory Structure
- `huf/ai/odoo/connector.py`: The core transport layer.
- `huf/ai/odoo/tool_handlers.py`: High-level ORM tool implementations.
- `huf/ai/odoo/schema.py`: Introspection and caching engine.
- `huf/ai/odoo/webhook.py`: Inbound signal receiver.
- `huf/ai/odoo/polling.py`: Fallback synchronization service.

## Integration Hooks
The skill is registered via the `huf_tools` hook in `hooks.py` and seeded via `huf.install.create_odoo_tools`.

## Usage for Agents
Agents should be equipped with the relevant `odoo_*` tools. The system prompt should instruct them to use `odoo_search_read` with Odoo Domain syntax (e.g., `[["is_company", "=", true]]`).
