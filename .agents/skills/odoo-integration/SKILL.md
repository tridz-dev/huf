---
name: Odoo Integration
description: First-class integration for Odoo ERP into the HUF AI system, supporting multi-protocol RPC and event synchronization.
---

# Odoo Integration Skill

This skill provides the HUF AI agents with the ability to interact with Odoo ERP instances using a robust, protocol-agnostic RPC engine.

## Core Capabilities

1.  **Multi-Protocol RPC**: Supports XML-RPC (Odoo < 12), JSON-RPC (Odoo 12-18), and JSON-2 (Odoo 19+).
2.  **Schema Discovery**: Automatic introspection and caching of Odoo models and fields.
3.  **Hybrid Sync**: Real-time webhooks (secured via Password keys) combined with an adaptive, async polling fallback (5-minute interval).
4.  **Domain Awareness**: Pre-built logic for CRM, Sales, and Inventory.
5.  **Smart Injection**: Auto-injection of connection parameters from Agent configuration to tools.

## Architecture & Patterns

### 1. Safe Invoke Pattern
All Odoo calls must use the `odoo_safe_invoke` decorator or follow its pattern to normalize internal exceptions.

### 2. Shared Rate Limiting
Uses a connection-scoped token-bucket limiter backed by Frappe's cache, ensuring RPM limits are respected across all background workers and concurrent tool calls.

### 3. O2M/M2M Command Array Pattern
When updating Odoo relational fields, use the standard command list format:
- `(0, 0, {values})`: Create new record
- `(1, id, {values})`: Update existing record
- `(2, id, 0)`: Delete/unlink record

### 4. Schema Discovery Pattern
Optimized O(1) indexing and error-swallowing for abstract models ensure schema discovery finishes gracefully without timing out the background worker.

## Directory Structure
- `huf/ai/odoo/connector.py`: The core transport layer with protocol auto-detection.
- `huf/ai/odoo/tool_handlers.py`: High-level ORM tool implementations.
- `huf/ai/odoo/rate_limiter.py`: Shared cache-based rate limiting logic.
- `huf/ai/odoo/schema.py`: Optimized introspection and caching engine.
- `huf/ai/odoo/webhook.py`: Secure inbound signal receiver.
- `huf/ai/odoo/polling.py`: Async fallback synchronization service.

## Integration Hooks
The skill is registered via the `huf_tools` hook in `hooks.py` and seeded via `huf.install.create_odoo_tools`.

## Usage for Agents
Agents should have the `odoo_connection` field set. The system prompt should instruct them to use `odoo_search_read` with Odoo Domain syntax. The `connection` parameter is automatically injected by the HUF SDK.
