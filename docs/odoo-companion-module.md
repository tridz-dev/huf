# Odoo Companion Module — Design Document

## Why This Exists

### Odoo Webhook Capability by Version

Odoo's webhook story has evolved significantly across versions:

| Odoo Version | Outbound Webhook Capability |
|---|---|
| **17** | `base.automation` adds **"External trigger"** — an inbound webhook URL that triggers an automation rule. No native *outbound* webhook action. Outbound still requires "Execute Code" with hand-written Python. |
| **18** | Dedicated **Webhooks** documentation + **"Send Webhook Notification"** as a first-class automation action type. This is the first version with true native outbound webhooks. |
| **19+** | Same as 18, more explicitly documented. |

> **HUF supports Odoo 17+ only.** Versions 15–16 are out of scope.

### What This Means for HUF

**For Odoo 18+**: Customers *can* use native "Send Webhook Notification" automation rules to push events to HUF's webhook receiver. However, this still requires:
1. One automation rule per model × event type (e.g., `sale.order` on create, `sale.order` on write = 2 rules)
2. Manual configuration for each model the customer wants to monitor
3. Admin-level access to Odoo's Settings → Technical → Automated Actions

**For Odoo 17**: No native outbound webhooks. The only options are:
- Hand-written Python in "Execute Code" automation actions (fragile, per-model)
- Polling from HUF's side (`write_date > last_sync` every 5 minutes)

**For all supported versions (17+)**: No Odoo customer gets event-driven integration "out of the box." HUF currently compensates with:

- **Polling** (`write_date > last_sync` every 5 minutes) — works everywhere, but laggy
- **Webhook receiver** — works if the customer manually configures automation rules (native on 18+, code snippets on 17)

### Why a Companion Module Is Still Valuable

Even with Odoo 18+'s native webhooks, the companion module provides:

1. **One-click setup** vs. creating N automation rules manually
2. **Consistent payload format** — native webhook payloads vary; the module ensures HUF gets exactly what it expects
3. **Bulk model coverage** — monitor 20 models with one wizard, not 40+ manual rules
4. **Odoo 17 support** — the only zero-config option for pre-18 versions
5. **Batched events** — deduplicates rapid successive writes before pushing to HUF
6. **Future-proof** — module handles version differences internally

---

## What the Companion Module Does

A single Odoo module (`huf_connector`) that:

1. **Auto-registers event listeners** on any model the user selects — no manual `base.automation` setup
2. **Pushes events in real-time** to HUF's webhook endpoint on create/write/unlink
3. **Covers all modules** without per-module code — uses Odoo's ORM signal system
4. **Provides a setup wizard** — enter HUF URL + webhook key, pick models to monitor, done
5. **Batches events** — avoids flooding HUF with one HTTP call per record save

---

## Module Structure

```
huf_connector/
├── __manifest__.py               # Module manifest
├── __init__.py
├── models/
│   ├── __init__.py
│   ├── huf_connection.py         # Connection settings (singleton)
│   ├── huf_monitored_model.py    # Which models to watch
│   └── huf_event_mixin.py       # ORM hook injection
├── wizards/
│   ├── __init__.py
│   └── huf_setup_wizard.py       # One-click setup
├── controllers/
│   ├── __init__.py
│   └── health.py                 # /huf/health endpoint for HUF to ping
├── data/
│   ├── ir_cron.xml               # Cron job for batch flush
│   └── common_models.xml         # Pre-populated model suggestions
├── views/
│   ├── huf_connection_views.xml  # Settings form
│   ├── huf_monitored_model_views.xml
│   └── huf_setup_wizard_views.xml
├── security/
│   └── ir.model.access.csv
└── static/
    └── description/
        └── icon.png
```

---

## Core Components

### 1. `huf_connection` — Singleton Settings Model

```python
# models/huf_connection.py
from odoo import models, fields, api

class HufConnection(models.Model):
    _name = "huf.connection"
    _description = "HUF Connection Settings"

    name = fields.Char(default="HUF Connection", required=True)
    huf_url = fields.Char("HUF Instance URL", required=True,
                          help="e.g., https://your-frappe-site.com")
    connection_name = fields.Char("Connection Name in HUF", required=True,
                                  help="Must match the Odoo Connection name in HUF")
    webhook_key = fields.Char("Webhook Key", required=True,
                              help="From Odoo Connection settings in HUF")
    is_active = fields.Boolean("Active", default=True)
    batch_mode = fields.Boolean("Batch Events", default=True,
                                help="Queue events and flush every N seconds instead of per-save")
    batch_interval = fields.Integer("Batch Interval (seconds)", default=5)
    last_push = fields.Datetime("Last Successful Push", readonly=True)
    status = fields.Selection([
        ("untested", "Not Tested"),
        ("connected", "Connected"),
        ("failed", "Failed"),
    ], default="untested", readonly=True)

    def action_test_connection(self):
        """Ping HUF's health endpoint to verify connectivity."""
        import requests
        url = f"{self.huf_url}/api/method/huf.ai.odoo.webhook.receive_webhook"
        try:
            resp = requests.head(url, timeout=10)
            self.status = "connected" if resp.status_code in (200, 405) else "failed"
        except Exception:
            self.status = "failed"
```

### 2. `huf_monitored_model` — What to Watch

```python
# models/huf_monitored_model.py
from odoo import models, fields

class HufMonitoredModel(models.Model):
    _name = "huf.monitored.model"
    _description = "Models monitored by HUF"

    connection_id = fields.Many2one("huf.connection", required=True, ondelete="cascade")
    model_id = fields.Many2one("ir.model", string="Odoo Model", required=True,
                               domain=[("transient", "=", False)])
    model_name = fields.Char(related="model_id.model", store=True, readonly=True)
    on_create = fields.Boolean("On Create", default=True)
    on_write = fields.Boolean("On Write", default=True)
    on_unlink = fields.Boolean("On Delete", default=False)
    include_record_data = fields.Boolean("Include Record Data in Payload", default=True,
                                         help="Send full record JSON. Disable for large records.")
    field_filter = fields.Char("Fields to Include",
                               help="Comma-separated. Empty = all fields.")
```

### 3. `huf_event_mixin` — The Core: ORM Hook Injection

This is the key piece. Instead of patching every model, we use Odoo's `BaseModel._register_hook()` mechanism and `ir.rule`-style monkey-patching to inject listeners at startup.

```python
# models/huf_event_mixin.py
import json
import logging
import threading
from collections import defaultdict
from odoo import models, api, SUPERUSER_ID

_logger = logging.getLogger(__name__)

# Thread-local event buffer for batching
_event_buffer = threading.local()


def _get_buffer():
    if not hasattr(_event_buffer, "events"):
        _event_buffer.events = defaultdict(list)
    return _event_buffer.events


def _push_event(env, model_name, event, ids, record_data=None):
    """Push event to HUF — either immediately or batched."""
    connections = env["huf.connection"].sudo().search([("is_active", "=", True)])
    if not connections:
        return

    for conn in connections:
        monitored = env["huf.monitored.model"].sudo().search([
            ("connection_id", "=", conn.id),
            ("model_name", "=", model_name),
        ], limit=1)

        if not monitored:
            continue

        # Check event type is enabled
        event_field = f"on_{event}"
        if not getattr(monitored, event_field, False):
            continue

        payload = {
            "model": model_name,
            "ids": ids,
            "event": f"on_{event}",
        }

        if monitored.include_record_data and record_data:
            payload["record_data"] = record_data

        if conn.batch_mode:
            buf = _get_buffer()
            buf[conn.id].append(payload)
        else:
            _send_to_huf(conn, payload)


def _send_to_huf(connection, payload):
    """HTTP POST to HUF webhook endpoint."""
    import requests
    url = (
        f"{connection.huf_url}/api/method/huf.ai.odoo.webhook.receive_webhook"
        f"?connection={connection.connection_name}&key={connection.webhook_key}"
    )
    try:
        resp = requests.post(url, json=payload, timeout=15)
        resp.raise_for_status()
        connection.sudo().write({"last_push": fields.Datetime.now()})
    except Exception as e:
        _logger.warning("HUF push failed for %s: %s", connection.connection_name, e)


def _flush_buffer(env):
    """Flush all batched events to HUF. Called by cron."""
    buf = _get_buffer()
    if not buf:
        return

    for conn_id, events in buf.items():
        if not events:
            continue
        try:
            conn = env["huf.connection"].sudo().browse(conn_id)
            if not conn.exists() or not conn.is_active:
                continue

            # Group by model for efficiency
            by_model = defaultdict(lambda: {"ids": [], "record_data": []})
            for evt in events:
                key = (evt["model"], evt["event"])
                by_model[key]["ids"].extend(evt["ids"])
                if "record_data" in evt:
                    by_model[key]["record_data"].extend(
                        evt["record_data"] if isinstance(evt["record_data"], list)
                        else [evt["record_data"]]
                    )

            for (model, event), data in by_model.items():
                payload = {
                    "model": model,
                    "ids": list(set(data["ids"])),  # deduplicate
                    "event": event,
                }
                if data["record_data"]:
                    payload["record_data"] = data["record_data"]
                _send_to_huf(conn, payload)
        except Exception as e:
            _logger.error("HUF batch flush error: %s", e)

    buf.clear()


class HufEventInjector(models.AbstractModel):
    """
    Registers ORM hooks on monitored models at server startup.
    Uses Odoo's _register_hook() which runs after all models are loaded.
    """
    _name = "huf.event.injector"
    _description = "HUF ORM Event Injector"

    @api.model
    def _register_hook(self):
        """
        Called by Odoo at registry build time.
        Patches create/write/unlink on all monitored models.
        """
        env = api.Environment(self.env.cr, SUPERUSER_ID, {})

        try:
            monitored = env["huf.monitored.model"].search([])
        except Exception:
            # Table may not exist yet during installation
            return

        patched_models = set()

        for mon in monitored:
            model_name = mon.model_name
            if model_name in patched_models:
                continue
            if model_name not in self.env:
                continue

            Model = self.env[model_name].__class__
            patched_models.add(model_name)

            # Save original methods
            orig_create = Model.create
            orig_write = Model.write
            orig_unlink = Model.unlink

            def make_create_hook(original, mname):
                @api.model_create_multi
                def hooked_create(self_inner, vals_list):
                    records = original(vals_list)
                    try:
                        data = records.read() if len(records) <= 20 else None
                        _push_event(self_inner.env, mname, "create",
                                    records.ids, record_data=data)
                    except Exception as e:
                        _logger.warning("HUF create hook error on %s: %s", mname, e)
                    return records
                return hooked_create

            def make_write_hook(original, mname):
                def hooked_write(self_inner, vals):
                    result = original(self_inner, vals)
                    try:
                        data = self_inner.read() if len(self_inner) <= 20 else None
                        _push_event(self_inner.env, mname, "write",
                                    self_inner.ids, record_data=data)
                    except Exception as e:
                        _logger.warning("HUF write hook error on %s: %s", mname, e)
                    return result
                return hooked_write

            def make_unlink_hook(original, mname):
                def hooked_unlink(self_inner):
                    ids = self_inner.ids  # Capture before deletion
                    result = original(self_inner)
                    try:
                        _push_event(self_inner.env, mname, "unlink", ids)
                    except Exception as e:
                        _logger.warning("HUF unlink hook error on %s: %s", mname, e)
                    return result
                return hooked_unlink

            Model.create = make_create_hook(orig_create, model_name)
            Model.write = make_write_hook(orig_write, model_name)
            Model.unlink = make_unlink_hook(orig_unlink, model_name)
```

### 4. Setup Wizard

```python
# wizards/huf_setup_wizard.py
from odoo import models, fields, api

COMMON_MODELS = [
    "res.partner", "crm.lead", "sale.order", "sale.order.line",
    "account.move", "account.move.line", "stock.picking", "stock.move",
    "purchase.order", "purchase.order.line", "project.task", "project.project",
    "hr.employee", "hr.leave", "helpdesk.ticket", "mrp.production",
]

class HufSetupWizard(models.TransientModel):
    _name = "huf.setup.wizard"
    _description = "HUF Quick Setup"

    huf_url = fields.Char("HUF Instance URL", required=True)
    connection_name = fields.Char("Connection Name", required=True)
    webhook_key = fields.Char("Webhook Key", required=True)
    module_scope = fields.Selection([
        ("common", "Common Models (CRM, Sales, Invoicing, Inventory)"),
        ("all_installed", "All Installed Modules"),
        ("manual", "I'll Pick Manually"),
    ], default="common", string="What to Monitor")

    def action_apply(self):
        # 1. Create or update connection
        conn = self.env["huf.connection"].search([], limit=1)
        if not conn:
            conn = self.env["huf.connection"].create({
                "huf_url": self.huf_url,
                "connection_name": self.connection_name,
                "webhook_key": self.webhook_key,
            })
        else:
            conn.write({
                "huf_url": self.huf_url,
                "connection_name": self.connection_name,
                "webhook_key": self.webhook_key,
            })

        # 2. Register models based on scope
        if self.module_scope == "common":
            models_to_add = COMMON_MODELS
        elif self.module_scope == "all_installed":
            models_to_add = self.env["ir.model"].search([
                ("transient", "=", False),
                ("model", "not like", "ir.%"),
                ("model", "not like", "base.%"),
            ]).mapped("model")
        else:
            return conn.action_open_monitored_models()

        IrModel = self.env["ir.model"]
        for model_name in models_to_add:
            ir_model = IrModel.search([("model", "=", model_name)], limit=1)
            if ir_model:
                existing = self.env["huf.monitored.model"].search([
                    ("connection_id", "=", conn.id),
                    ("model_id", "=", ir_model.id),
                ])
                if not existing:
                    self.env["huf.monitored.model"].create({
                        "connection_id": conn.id,
                        "model_id": ir_model.id,
                    })

        # 3. Test connection
        conn.action_test_connection()

        # 4. Restart registry to activate hooks
        self.env.registry.signal_changes()

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "HUF Connected",
                "message": f"Monitoring {len(models_to_add)} models. Events will push to HUF in real-time.",
                "type": "success",
            }
        }
```

### 5. Cron Job for Batch Flush

```xml
<!-- data/ir_cron.xml -->
<?xml version="1.0" encoding="UTF-8"?>
<odoo>
    <record id="huf_event_flush_cron" model="ir.cron">
        <field name="name">HUF: Flush Event Buffer</field>
        <field name="model_id" ref="model_huf_event_injector"/>
        <field name="code">env["huf.event.injector"]._flush_buffer()</field>
        <field name="interval_number">5</field>
        <field name="interval_type">seconds</field>
        <field name="active">True</field>
        <field name="numbercall">-1</field>
    </record>
</odoo>
```

### 6. Module Manifest

```python
# __manifest__.py
{
    "name": "HUF Connector",
    "version": "1.0.0",  # Version per Odoo target in separate branches (17.0, 18.0, 19.0)
    "category": "Technical",
    "summary": "Real-time event bridge between Odoo and HUF AI platform",
    "description": """
        Pushes Odoo ORM events (create/write/unlink) to HUF's webhook endpoint
        in real-time. Eliminates the need for polling or manual base.automation setup.

        Works with all Odoo modules — CRM, Sales, Invoicing, Inventory, HR, etc.
    """,
    "author": "Tridz Technologies",
    "website": "https://github.com/tridz-dev/huf",
    "license": "MIT",
    "depends": ["base"],  # No other dependencies — works with any Odoo installation
    "data": [
        "security/ir.model.access.csv",
        "data/ir_cron.xml",
        "views/huf_connection_views.xml",
        "views/huf_monitored_model_views.xml",
        "views/huf_setup_wizard_views.xml",
    ],
    "installable": True,
    "auto_install": False,
    "application": False,
}
```

---

## How It Covers All Modules

The key insight: **we don't write per-module code**. The `_register_hook()` mechanism patches the ORM methods (`create`, `write`, `unlink`) on whatever models the user selects via `huf.monitored.model`. This means:

| Odoo Module | Covered? | How |
|-------------|----------|-----|
| CRM | Yes | Monitor `crm.lead`, `crm.team` |
| Sales | Yes | Monitor `sale.order`, `sale.order.line` |
| Invoicing | Yes | Monitor `account.move`, `account.move.line` |
| Inventory | Yes | Monitor `stock.picking`, `stock.move` |
| Purchase | Yes | Monitor `purchase.order`, `purchase.order.line` |
| HR | Yes | Monitor `hr.employee`, `hr.leave` |
| Project | Yes | Monitor `project.task`, `project.project` |
| Helpdesk | Yes | Monitor `helpdesk.ticket` |
| Manufacturing | Yes | Monitor `mrp.production`, `mrp.workorder` |
| Custom/Studio models | Yes | Monitor any `x_*` model |
| **Any future module** | **Yes** | Just add the model to monitored list |

The setup wizard pre-populates common models, but the user can add **any model** from any installed module.

---

## Integration Strategy by Odoo Version

There are **three** paths to get events from Odoo to HUF, and the right one depends on the customer's Odoo version and hosting:

### Path A: Native Webhooks (Odoo 18+)
Odoo 18 introduced **"Send Webhook Notification"** as a first-class automation action. Customers can:
1. Go to Settings → Technical → Automated Actions
2. Create a rule: "When sale.order is created → Send Webhook Notification to HUF URL"
3. Repeat for each model × event combination

**Pros**: Zero custom code, works on Odoo.com SaaS (Custom plan), officially supported.
**Cons**: Manual setup per model × event (20 models × 2 events = 40 rules), payload format is Odoo's native format (may need normalization on HUF side).

### Path B: Companion Module (Odoo 17+, self-hosted / Odoo.sh)
The `huf_connector` module described in this document.

**Pros**: One-click setup, consistent payload format, works on 17-19+, batching, bulk coverage.
**Cons**: Requires ability to install custom modules (not possible on Odoo.com SaaS Standard).

### Path C: Polling Fallback (All versions, all hosting)
HUF's built-in `write_date > last_sync` polling every 5 minutes.

**Pros**: Works everywhere, zero Odoo-side configuration.
**Cons**: 5-minute latency, can't detect deletes, wastes queries when nothing changed.

### Decision Matrix

| Customer Setup | Recommended Path | Fallback |
|---|---|---|
| **Odoo 18+ on Odoo.com (Custom plan)** | A (Native Webhooks) | C (Polling) |
| **Odoo 18+ on Odoo.com (Standard plan)** | C (Polling only) | — |
| **Odoo 18+ on Odoo.sh / self-hosted** | B (Companion Module) | A (Native Webhooks) |
| **Odoo 17 on Odoo.sh / self-hosted** | B (Companion Module) | C (Polling) |
| **Odoo 17 on Odoo.com** | C (Polling only) | — |

## Current HUF Approach vs. Companion Module

| Aspect | Polling | Native Webhooks (18+) | Companion Module |
|--------|---------|----------------------|-----------------|
| **Latency** | 5 min | Real-time | Real-time (sub-second) |
| **Setup effort** | Zero | 1 rule per model × event | Install module → run wizard → done |
| **Module coverage** | All (via write_date) | Manual per model | All models, one click |
| **Odoo SaaS** | Works | Works (Custom plan, 18+) | **Not supported** |
| **Odoo Community** | Works | No (base_automation is Enterprise) | Works |
| **Odoo.sh / Self-hosted** | Works | Works (18+) | Works |
| **Detect deletes** | No | Yes (if configured) | Yes |
| **Payload consistency** | N/A | Odoo's native format | HUF-optimized format |
| **Reliability** | Can miss rapid changes | Per-event | Every ORM event captured |
| **Load on Odoo** | Queries every 5 min | Zero when idle | Zero when idle |

**Conclusion**: The companion module is the best path for Odoo.sh and self-hosted customers (any version). Native webhooks are a good alternative for Odoo 18+ customers who prefer no custom modules. Polling remains the universal fallback.

---

## Migrating to `odoo-client-lib`

HUF currently hand-rolls the transport layer (~200 lines across `protocols/` + `connector.py`). `odoo-client-lib` wraps XML-RPC, JSON-RPC, and JSON-2 with protocol auto-detection, secure variants (TLS), and community-tested version coverage (8.0+ JSON-RPC, 19.0+ JSON-2). Since we target 17+ only, this is a clean fit.

### Why adopt it

| | Hand-rolled (current) | `odoo-client-lib` |
|---|---|---|
| Code to maintain | ~200 lines (protocols + connector) | ~50 lines of adapter |
| Protocol auto-detect | Our own logic in `_resolve_protocol()` | Built-in from version info |
| Secure transport (TLS) | Not implemented | `jsonrpcs://`, `json2s://` for free |
| Error normalization | Manual per-protocol exception handling | Consistent across transports |
| Dependency | Zero | One PyPI package |

### Migration Steps

**Step 1 — Add dependency**

```diff
# pyproject.toml
dependencies = [
    "openai-agents",
    "litellm>=1.0.0",
    "llama-index-core>=0.10.0",
    "sqlite-vec",
    "pysqlite3-binary",
+   "odoo-client-lib",
]
```

Then `bench setup requirements`.

**Step 2 — Rewrite `connector.py` (the only file that changes its internals)**

Replace `_resolve_protocol()` + `_init_transport()` with `odoo_client_lib.get_connection()`. The public API of `OdooConnector` stays identical — all callers (`tool_handlers.py`, `webhook.py`, `polling.py`, `schema.py`) are untouched.

```python
# huf/ai/odoo/connector.py — after migration
import frappe
from typing import Any, List, Dict, Optional
from .rate_limiter import RateLimiter
from .exceptions import OdooAuthError, OdooConnectionError

import odoo_client_lib as odoo_lib


class OdooConnector:
	"""
	Protocol-agnostic connector to Odoo instances.
	Uses odoo-client-lib for transport; handles rate limiting.
	"""

	def __init__(self, connection_name: str):
		self.connection = frappe.get_doc("Odoo Connection", connection_name)
		self.url = self.connection.odoo_url
		self.db = self.connection.database_name
		self.username = self.connection.username
		self.api_key = self.connection.get_password("api_key")
		self.uid = self.connection.user_id

		# Let odoo-client-lib pick the right protocol
		protocol = self._resolve_protocol_string()
		try:
			self._conn = odoo_lib.get_connection(
				hostname=self.url.rstrip("/"),
				protocol=protocol,
				database=self.db,
				login=self.username,
				password=self.api_key,
			)
			self._conn.check_login(force=False)
		except Exception as e:
			raise OdooConnectionError(f"Failed to connect: {e}") from e

		self.rate_limiter = RateLimiter(connection_name, self.connection.rate_limit_rpm or 60)

	def _resolve_protocol_string(self) -> str:
		"""Map our DocType field values to odoo-client-lib protocol strings."""
		explicit = self.connection.protocol
		if explicit and explicit != "Auto":
			return {
				"JSON-RPC": "jsonrpc",
				"XML-RPC": "xmlrpc",
				"JSON-2": "json2",
			}.get(explicit, "jsonrpc")

		version = self.connection.odoo_version
		try:
			if version and version != "Auto Detect" and int(version) >= 19:
				return "json2"
		except (ValueError, TypeError):
			pass
		return "jsonrpc"

	def execute(self, model: str, method: str, *args, **kwargs) -> Any:
		self.rate_limiter.wait()
		model_proxy = self._conn.get_model(model)
		return getattr(model_proxy, method)(*args, **kwargs)

	# --- Public helpers (unchanged signatures) ---

	def search_read(self, model: str, domain: Optional[List] = None,
	                fields: Optional[List] = None, limit: int = 80,
	                offset: int = 0, order: Optional[str] = None) -> List[Dict]:
		return self.execute(
			model, "search_read",
			domain or [],
			fields=fields, limit=limit, offset=offset, order=order,
		)

	def create(self, model: str, values: Dict) -> int:
		return self.execute(model, "create", [values])

	def write(self, model: str, ids: List[int], values: Dict) -> bool:
		return self.execute(model, "write", [ids, values])

	def unlink(self, model: str, ids: List[int]) -> bool:
		return self.execute(model, "unlink", [ids])

	def fields_get(self, model: str, attributes: Optional[List] = None) -> Dict:
		return self.execute(
			model, "fields_get", [],
			attributes=attributes or ["string", "type", "required", "help", "relation"],
		)

	def get_models(self) -> List[Dict]:
		return self.search_read("ir.model", fields=["model", "name"])
```

**Step 3 — Delete the `protocols/` directory**

These files become dead code:
- `huf/ai/odoo/protocols/__init__.py`
- `huf/ai/odoo/protocols/xmlrpc.py` (25 lines)
- `huf/ai/odoo/protocols/jsonrpc.py` (40 lines)
- `huf/ai/odoo/protocols/json2.py` (42 lines)

Remove the entire `protocols/` directory.

**Step 4 — Clean up `exceptions.py`**

`OdooRPCError` and `OdooJSON2Error` were only raised inside `protocols/`. After deletion:
- Keep: `OdooConnectionError`, `OdooAuthError`, `OdooRateLimitError`, `OdooModelNotFoundError`
- Remove: `OdooRPCError`, `OdooJSON2Error`

`odoo-client-lib` raises its own transport errors; catch those in `tool_handlers.py`'s `odoo_safe_invoke` decorator.

**Step 5 — Update `odoo_safe_invoke` in `tool_handlers.py`**

```diff
  @wraps(fn)
  def wrapper(*args, **kwargs):
      try:
          return fn(*args, **kwargs)
      except OdooAuthError as e:
          return {"success": False, "error": str(e), "suggestion": "Check credentials"}
      except OdooRateLimitError as e:
          return {"success": False, "error": str(e), "suggestion": "Wait and retry"}
-     except OdooRPCError as e:
-         return {"success": False, "error": str(e), "suggestion": "Check parameters"}
-     except OdooJSON2Error as e:
-         return {"success": False, "error": str(e), "suggestion": "Check parameters"}
+     except odoo_lib.Error as e:
+         return {"success": False, "error": str(e), "suggestion": "Check parameters"}
      except Exception as e:
          return {"success": False, "error": str(e), "suggestion": "Unexpected error"}
```

**Step 6 — Update `odoo_connection.py` test_connection()**

The `test_connection()` method in the DocType controller currently uses raw `xmlrpc.client` directly. Replace with `odoo_client_lib.get_connection()` so it uses the same transport path.

**Step 7 — Verify**

- Zero callers change: `tool_handlers.py`, `webhook.py`, `polling.py`, `schema.py` all call `OdooConnector` methods (`search_read`, `create`, `write`, `execute`, etc.) which keep the same signatures.
- Run `bench --site <site> run-tests --app huf` to confirm.

### Files touched (summary)

| File | Action |
|---|---|
| `pyproject.toml` | Add `odoo-client-lib` |
| `huf/ai/odoo/connector.py` | Rewrite internals, same public API |
| `huf/ai/odoo/protocols/` | **Delete entire directory** (4 files) |
| `huf/ai/odoo/exceptions.py` | Remove `OdooRPCError`, `OdooJSON2Error` |
| `huf/ai/odoo/tool_handlers.py` | Update `odoo_safe_invoke` catch clause |
| `huf/huf/doctype/odoo_connection/odoo_connection.py` | Update `test_connection()` |

**Zero changes needed** in: `webhook.py`, `polling.py`, `schema.py`, `agents_seed.py`, `rate_limiter.py`, `install.py`, any frontend code.

---

## HUF-Side Changes Needed

When the companion module is built, HUF's webhook receiver (`huf/ai/odoo/webhook.py`) already handles the payload format. No changes needed on the HUF side except:

1. **Document the companion module** in Odoo Connection setup UI (link to install instructions)
2. **Auto-disable polling** for connections that have the companion module active (detect via a heartbeat/health ping)
3. **Handle batched payloads** — the companion module may send multiple IDs per event; `webhook.py` already supports this via the `ids` list

---

## Implementation Priority

1. **Phase 1**: Core module (`huf.connection`, `huf.monitored.model`, ORM hooks, setup wizard)
2. **Phase 2**: Batch mode with cron flush, health endpoint
3. **Phase 3**: Field-level change tracking (send old vs. new values)
4. **Phase 4**: Odoo.com App Store listing for discoverability
