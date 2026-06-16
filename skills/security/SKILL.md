---
name: security
category: patterns
description: Security and permissions framework for HUF AI agent platform
---

# Security & Permissions

HUF implements a comprehensive, multi-layered security framework that protects against common vulnerabilities while providing granular access control for AI agents, tools, and workflows.

## Overview

The security architecture follows defense-in-depth principles with the following layers:

1. **Network Security** - SSRF protection, URL validation
2. **Credential Security** - Encrypted storage, environment variables
3. **Access Control** - Role-based permissions (RBAC), capability system
4. **Tool Security** - Permission-aware tool registry, mutating operation guards
5. **Flow Security** - Safe expression evaluation, hop limits
6. **Guest Restrictions** - Limited access for unauthenticated users

## Key Files

| File | Purpose |
|------|---------|
| `huf/ai/http_handler.py` | SSRF protection, URL validation, secure HTTP requests |
| `huf/ai/flow_eval.py` | Safe AST-based expression evaluator for flow conditions |
| `huf/ai/sdk_tools.py` | Tool execution with permission checks, `_check_tool_permission()` |
| `huf/ai/tool_registry.py` | `PermissionAwareToolRegistry` - filters tools by user permissions |
| `huf/ai/permissions_api.py` | Whitelisted API endpoints for user/role management with capability checks |
| `huf/permissions.py` | Core permission layer: capabilities, roles, caching |
| `huf/huf/doctype/huf_role/huf_role.py` | Huf Role DocType with capability validation |
| `huf/huf/doctype/huf_user_role/huf_user_role.py` | User-role bridge with Frappe role sync |
| `huf/huf/doctype/huf_role_permission/huf_role_permission.py` | Permission child table with labels |

## How It Works

### 1. SSRF Protection (`huf/ai/http_handler.py`)

The `validate_url()` function prevents Server-Side Request Forgery attacks:

```python
def validate_url(url, tool_name=None):
    # Parse the URL
    parsed = urlparse(url)
    
    # Block private IP addresses
    private_ip_pattern = re.compile(
        r'^(127\.|10\.|172\.1[6-9]\.|172\.2[0-9]\.|172\.3[0-1]\.|192\.168\.)'
    )
    
    if private_ip_pattern.match(parsed.hostname):
        return False
        
    if parsed.hostname in ['localhost', '127.0.0.1', '::1']:
        return False
    
    # Allow only HTTP and HTTPS
    if parsed.scheme not in ['http', 'https']:
        return False
    
    # Validate against tool's base URL if specified
    if tool_name:
        tool_doc = frappe.get_doc("Agent Tool Function", tool_name)
        if tool_doc.base_url:
            tool_parsed = urlparse(tool_doc.base_url)
            if parsed.netloc != tool_parsed.netloc:
                return False
    
    return True
```

**Key Protections:**
- Blocks private IP ranges: `127.*`, `10.*`, `172.16-31.*`, `192.168.*`
- Blocks localhost variants: `localhost`, `127.0.0.1`, `::1`
- Protocol restriction: Only `http` and `https` allowed
- Base URL validation: Tools can restrict requests to specific domains

### 2. Credential Security

#### Encrypted Storage

API keys and authentication tokens are stored using Frappe's `Password` field type:

```python
# AI Provider - API key encrypted
api_key = provider_doc.get_password("api_key")

# MCP Server - Auth token encrypted
auth_token = mcp_server_doc.get_password("auth_header_value")
```

#### Environment Variables

Sensitive keys for specific providers use environment variables:

```python
# providers/litellm.py
_TTS_ENV_VAR_PROVIDERS = {
    "google":     "GEMINI_API_KEY",
    "elevenlabs": "ELEVENLABS_API_KEY",
    "minimax":    "MINIMAX_API_KEY",
}
```

### 3. Role-Based Access Control (`huf/permissions.py`)

#### Capability System

HUF uses a capability-based permission model:

```python
CAPABILITIES = {
    # Agents
    "agent.use": "Use Agents",
    "agent.create": "Create Agents",
    "agent.edit": "Edit Agents",
    "agent.delete": "Delete Agents",
    # Tools
    "tools.use": "Use Tools",
    "tools.create": "Create Tools",
    # Flows
    "flows.use": "Use Flows",
    "flows.create": "Create Flows",
    # Users & Roles
    "users.invite": "Invite Users",
    "users.manage": "Manage Users",
    "roles.manage": "Manage Roles",
    # ... etc
}
```

#### Default Role Capabilities

```python
DEFAULT_ROLE_CAPABILITIES = {
    "Huf Admin": list(CAPABILITIES.keys()),  # All capabilities
    "Huf Manager": [
        "agent.use", "agent.create", "agent.edit", "agent.delete",
        "tools.use", "tools.create", "tools.manage",
        "flows.use", "flows.create", "flows.manage",
        "users.invite", "users.manage",
    ],
    "Huf User": [
        "agent.use", "chat.use", "knowledge.use", "tools.use", "flows.use",
    ],
    "Huf Viewer": ["agent.use", "chat.view_own"],
}
```

#### Frappe Role Mapping

```python
HUF_ROLE_FRAPPE_ROLE_MAP = {
    "Huf Admin": "System Manager",
    "Huf Manager": "Huf Manager",
    "Huf User": "Huf User",
    "Huf Viewer": "Huf Viewer",
}
```

#### Permission Checking

```python
from huf.permissions import has_capability, get_user_capabilities

# Check single capability
if not has_capability(frappe.session.user, "agent.create"):
    frappe.throw(_("Not permitted"), frappe.PermissionError)

# Get all user capabilities
caps = get_user_capabilities(user)
# Returns: ["agent.use", "chat.use", "tools.use", ...]
```

### 4. Tool Permission Registry (`huf/ai/tool_registry.py`)

#### PermissionAwareToolRegistry

Filters tools based on user permissions before agent execution:

```python
class PermissionAwareToolRegistry:
    TOOL_PERMISSIONS = {
        "Get Document": {"permission": "read"},
        "Get List": {"permission": "read"},
        "Create Document": {"permission": "create"},
        "Update Document": {"permission": "write"},
        "Delete Document": {"permission": "delete"},
        "Submit Document": {"permission": "submit"},
        "Cancel Document": {"permission": "cancel"},
    }
    
    MUTATING_TOOL_TYPES = {
        "Create Document", "Create Multiple Documents",
        "Update Document", "Update Multiple Documents", 
        "Delete Document", "Delete Multiple Documents",
        "Submit Document", "Cancel Document",
        "Set Value", "POST", "Run Agent",
        "Attach File to Document"
    }
```

#### Permission Check Logic

```python
def _can_use_tool(cls, tool_doc, user: str) -> bool:
    tool_type = tool_doc.types
    
    # Read Only restriction
    if tool_doc.is_read_only and tool_type in cls.MUTATING_TOOL_TYPES:
        return False
    
    # Guest Restrictions
    if user == "Guest":
        if bool(tool_doc.allowed_for_guest):
            return True
        if tool_type in cls.MUTATING_TOOL_TYPES:
            return False
        return False
    
    # DocType Permission Checks
    if tool_doc.reference_doctype:
        perm_type = tool_doc.required_permission or cls.TOOL_PERMISSIONS.get(tool_type, {}).get("permission")
        if perm_type:
            if not frappe.has_permission(doctype=tool_doc.reference_doctype, ptype=perm_type, user=user):
                return False
    
    return True
```

### 5. Tool Execution Guards (`huf/ai/sdk_tools.py`)

#### Pre-Execution Permission Check

```python
async def on_invoke_tool(ctx=None, args_json: str = None) -> str:
    # Permission check before execution
    if tool_type:
        perm_check = _check_tool_permission(tool_type, ctx, allowed_for_guest=allowed_for_guest)
        if not perm_check["allowed"]:
            return json.dumps({"error": perm_check["error"], "denied": True})
    
    # ... execute tool
```

#### Guest User Restrictions

```python
def _check_tool_permission(tool_type: str, context: dict = None, allowed_for_guest: bool = False):
    """Guard function to block dangerous tools for Guest users"""
    user = frappe.session.user
    
    # Guest cannot use mutating tools unless explicitly allowed
    if user == "Guest":
        if allowed_for_guest:
            return {"allowed": True}
             
        if tool_type in MUTATING_TOOL_TYPES:
            return {
                "allowed": False,
                "error": f"Guest users cannot use {tool_type} tools. Please log in."
            }
    
    return {"allowed": True}
```

#### DocType-Level Permission Checks

```python
def handle_create_document(reference_doctype=None, ignore_permissions=False, **kwargs):
    if not ignore_permissions and not frappe.has_permission(reference_doctype, "create"):
        return {
            "success": False,
            "error": f"You do not have permission to create {reference_doctype}",
            "permission_denied": True
        }
    # ... create document

def handle_delete_document(document_id=None, reference_doctype=None, ignore_permissions=False, **kwargs):
    if not ignore_permissions and not frappe.has_permission(reference_doctype, "delete", doc=document_id):
        return {
            "success": False,
            "error": f"You do not have delete permission on {reference_doctype} {document_id}",
            "permission_denied": True
        }
    # ... delete document
```

### 6. Safe Expression Evaluation (`huf/ai/flow_eval.py`)

Flow expression edges use a restricted AST evaluator:

```python
def safe_eval_expression(expression: str, context: dict) -> bool:
    """
    Safely evaluate an expression string against flow context.
    
    Only allows:
    - Dict key access: context["key"]
    - Comparisons: ==, !=, <, >, <=, >=, in, not in
    - Boolean operators: and, or, not
    - Literals: strings, numbers, booleans, None, lists, dicts
    - Simple arithmetic: +, -, *, %
    
    Does NOT allow:
    - Function calls
    - Attribute access (no dot notation)
    - Import statements
    - Assignment
    """
    tree = ast.parse(expression, mode="eval")
    result = _eval_node(tree.body, {"context": context})
    return bool(result)
```

#### Allowed Operations

```python
SAFE_OPS = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Mod: operator.mod,
    ast.Not: operator.not_,
}
```

#### Security Restrictions

- Maximum expression length: 500 characters
- No function calls (`ast.Call` raises ValidationError)
- No attribute access (`ast.Attribute` raises ValidationError)
- Only `context` variable is available in scope
- All comparisons are validated against allowed operators

### 7. Permission API Endpoints (`huf/ai/permissions_api.py`)

All endpoints enforce capability checks:

```python
def _require(capability: str) -> None:
    """Throw a PermissionError if the current user lacks *capability*."""
    if not has_capability(frappe.session.user, capability):
        frappe.throw(_("You don't have permission to perform this action."), 
                     frappe.PermissionError)

@frappe.whitelist()
def invite_user(email: str, full_name: str, huf_role: str) -> dict:
    _require("users.invite")
    # ... invite logic

@frappe.whitelist()
def create_huf_role(role_name: str, description: str, capabilities: list) -> dict:
    _require("roles.manage")
    # ... role creation
```

### 8. Cache Management

User capabilities are cached for performance:

```python
_CACHE_KEY_PREFIX = "huf_user_capabilities"

def _cache_key(user: str) -> str:
    return f"{_CACHE_KEY_PREFIX}::{user}"

def _bust_cache(user: str) -> None:
    frappe.cache().delete_value(_cache_key(user))

def get_user_capabilities(user: str | None = None) -> list[str]:
    cached = frappe.cache().get_value(_cache_key(user))
    if cached is not None:
        return cached
    
    # ... fetch from database
    frappe.cache().set_value(_cache_key(user), result, expires_in_sec=300)
    return result
```

Cache is busted when:
- User role is updated (`HufUserRole.on_update()`)
- Role capabilities are changed (`HufRole.on_update()`)

## Extension Points

### Adding New Capabilities

1. Add to `CAPABILITIES` dictionary in `huf/permissions.py`:

```python
CAPABILITIES = {
    # ... existing capabilities
    "myfeature.manage": "Manage My Feature",
}
```

2. Use in your code:

```python
from huf.permissions import has_capability

if not has_capability(frappe.session.user, "myfeature.manage"):
    frappe.throw(_("Not permitted"), frappe.PermissionError)
```

### Custom Tool Permission Logic

Extend `PermissionAwareToolRegistry`:

```python
from huf.ai.tool_registry import PermissionAwareToolRegistry

class CustomToolRegistry(PermissionAwareToolRegistry):
    CUSTOM_PERMISSIONS = {
        "My Custom Tool": {"permission": "custom_perm"},
    }
    
    @classmethod
    def _can_use_tool(cls, tool_doc, user: str) -> bool:
        # Custom logic
        if tool_doc.types == "My Custom Tool":
            return has_custom_access(user)
        return super()._can_use_tool(tool_doc, user)
```

### Custom URL Validators

Extend SSRF protection:

```python
from huf.ai.http_handler import validate_url

def validate_url_custom(url, tool_name=None):
    # First run standard validation
    if not validate_url(url, tool_name):
        return False
    
    # Add custom checks
    parsed = urlparse(url)
    if parsed.hostname.endswith(".internal.company.com"):
        return False
    
    return True
```

## Dependencies

- **Frappe Framework**: Core permission system, Password field type, caching
- **Python AST**: Safe expression evaluation (`ast` module)
- **urllib**: URL parsing for SSRF protection
- **re**: Regex patterns for IP validation

## Gotchas

### 1. Guest Tool Access

Tools must explicitly enable `allowed_for_guest` for Guest users:

```python
# In Agent Tool Function document
allowed_for_guest = 1  # Check this field
```

Even with this flag, mutating tools are blocked unless `ignore_permissions` is handled carefully.

### 2. Permission Caching

User capabilities are cached for 5 minutes (300 seconds). After role changes, users may need to wait or log out/in for changes to take effect.

### 3. Flow Expression Limitations

Flow expressions cannot use:
- Method calls: `context.get("key")` ❌
- Attribute access: `context.key` ❌
- Function calls: `len(context.items)` ❌

Use only: `context["key"]`, `context["key"] == "value"`, `context["count"] > 5`

### 4. Custom Functions Run as User

Custom tool functions registered via `huf_tools` hook run with the permissions of the calling user. Always validate inputs and check permissions inside custom functions:

```python
def my_custom_tool(doctype, name):
    if not frappe.has_permission(doctype, "read", doc=name):
        return {"error": "Permission denied"}
    # ... proceed
```

### 5. Webhook Security

Webhook triggers use `webhook_key` for authentication. Store these securely:

```python
# In Agent Trigger document
webhook_key = "secure_random_string"  # Treat as password
```

### 6. File Upload Restrictions

File attachments via tools validate:
- File type restrictions
- File size limits (Frappe default)
- Storage quotas

### 7. HTTP Timeout

All HTTP requests from tools have a 30-second timeout:

```python
request_kwargs = {
    'timeout': 30  # Prevents hanging requests
}
```

### 8. System Roles Protection

System roles (`is_system_role=1`) cannot be deleted:

```python
def on_trash(self):
    if self.is_system_role:
        frappe.throw(_("'{0}' is a system role and cannot be deleted.").format(self.role_name),
                     frappe.PermissionError)
```
