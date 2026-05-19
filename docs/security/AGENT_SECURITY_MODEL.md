# HUF Agent Security Model Analysis

> **Document Status**: Analysis & Improvement Plan  
> **Last Updated**: February 2026  
> **Priority**: CRITICAL

## Executive Summary

This document analyzes the current security model of the HUF agent system and provides a comprehensive plan to address identified vulnerabilities. The core issue is that **agents currently operate without proper identity binding and permission enforcement**, effectively bypassing Frappe's authentication boundaries.

**Key Principle:**
> Agents don't have power. Users have power. Agents only borrow it — explicitly.

---

## Table of Contents

1. [Current Architecture Analysis](#current-architecture-analysis)
2. [Identified Security Weaknesses](#identified-security-weaknesses)
3. [Immediate Fixes (Short-term)](#immediate-fixes-short-term)
4. [Medium-term Improvements](#medium-term-improvements)
5. [Long-term Security Model](#long-term-security-model)
6. [Implementation by Component](#implementation-by-component)
7. [Security Checklist](#security-checklist)

---

## Current Architecture Analysis

### How Agents Handle DocType Access

#### Tool Execution Flow

```
User/API Request
      │
      ▼
run_agent_sync() [allow_guest=True]
      │
      ├─► Check: allow_guest flag on Agent
      │
      ▼
AgentManager._setup_tools()
      │
      ├─► Load MCP tools (no permission filtering)
      ├─► Load Native tools (no permission filtering)
      │
      ▼
LLM decides which tools to call
      │
      ▼
Tool Execution (on_invoke_tool)
      │
      ├─► tool_functions.py handlers
      │   └─► Frappe CRUD operations
      │
      ▼
Result returned to LLM
```

#### Current Permission Checks by Tool Type

| Tool Type | Permission Check | Status |
|-----------|------------------|--------|
| `Get Document` | `doc.check_permission()`, `apply_fieldlevel_read_permissions()` | ✅ GOOD |
| `Get List` | `frappe.get_list()` (implicit read perms) | ✅ GOOD |
| `Get Value` | `frappe.db.get_value()` (no perm check) | ⚠️ WEAK |
| `Create Document` | None - relies on `doc.insert()` implicit | ❌ MISSING |
| `Update Document` | None - relies on `doc.save()` implicit | ❌ MISSING |
| `Delete Document` | None - relies on `frappe.delete_doc()` | ❌ MISSING |
| `Submit Document` | None - relies on `doc.submit()` implicit | ❌ MISSING |
| `Cancel Document` | None - relies on `doc.cancel()` implicit | ❌ MISSING |
| `Attach File` | `frappe.has_permission(ptype="write")` | ✅ GOOD |
| `HTTP Request (GET/POST)` | SSRF validation only | ⚠️ PARTIAL |
| `MCP Tools` | None | ❌ MISSING |
| `Custom Functions` | None (user responsibility) | ⚠️ VARIES |

#### Agent DocType Security Fields (Existing but Underutilized)

```python
# From agent.json
{
    "allow_guest": Check,           # Only checked at entry point
    "allowed_users": Table,         # NOT enforced at runtime
    "allowed_roles": Table,         # NOT enforced at runtime
}
```

---

## Identified Security Weaknesses

### 1. Guest Access with Full Tool Capabilities

**Vulnerability**: `run_agent_sync()` is decorated with `@frappe.whitelist(allow_guest=True)`

```python
# Current code (agent_integration.py:438)
@frappe.whitelist(allow_guest=True)
def run_agent_sync(agent_name, prompt, ...):
    # Only check: does agent allow guest?
    if frappe.session.user == "Guest" and not agent_doc.allow_guest:
        frappe.throw(...)
    # If allow_guest=True, Guest can use ALL tools!
```

**Risk**: If an agent has `allow_guest=True`, a Guest user can:
- Create Sales Orders
- Delete Customer records  
- Submit invoices
- Access sensitive data

### 2. No Pre-Execution Permission Validation

**Vulnerability**: CRUD tools don't validate permissions before execution.

```python
# Current code (tool_functions.py:31)
def create_document(doctype: str, data: dict, function=None):
    # NO permission check here!
    doc = frappe.get_doc({"doctype": doctype, **data})
    doc.insert()  # Relies on Frappe's implicit check
    return {...}
```

**Risk**: While Frappe's `insert()` does check permissions, the error is:
1. Not user-friendly for AI (returns exception, not structured error)
2. Happens after processing (wastes resources)
3. No pre-filtering of tools based on permissions

### 3. No Execution Identity Binding

**Vulnerability**: No concept of "who" the agent is acting as.

```python
# Current behavior:
# - Tool runs as frappe.session.user (whoever called the API)
# - Doc event agent runs as whoever triggered the event
# - Scheduled agent runs as Administrator (or scheduler user)
# - No explicit "execution_identity" concept
```

**Risk**: 
- Audit trails are inconsistent
- Privilege escalation via scheduled agents
- No ability to restrict agent actions to specific roles

### 4. Tool Visibility Without Permission Filtering

**Vulnerability**: All agent tools are visible to the LLM regardless of user permissions.

```python
# Current code (sdk_tools.py:27)
def create_agent_tools(agent) -> list[FunctionTool]:
    tools = []
    # Load ALL MCP tools
    # Load ALL native tools
    # No filtering based on user permissions!
    return tools
```

**Risk**: LLM can attempt operations the user cannot perform, leading to:
- Confusing error messages
- Potential partial operations before failure
- Information leakage (tool names reveal capabilities)

### 5. MCP Tools Execute Without Validation

**Vulnerability**: MCP tool execution has zero permission checks.

```python
# Current code (mcp_client.py:199)
async def execute_mcp_tool(server_name, tool_name, arguments):
    # NO permission checks
    # NO user validation
    # Directly calls external MCP server
    return await _execute_mcp_tool_http(...)
```

**Risk**: External MCP servers can be called by any user with agent access.

### 6. allowed_users/allowed_roles Not Enforced

**Vulnerability**: Agent has permission fields but they're not checked.

```python
# Fields exist in Agent DocType:
# - allowed_users (Table MultiSelect)
# - allowed_roles (Table MultiSelect)

# But NO code enforces these!
```

---

## Immediate Fixes (Short-term)

### Priority 1: Block Mutating Tools for Guest Users

**Implementation Location**: `huf/ai/sdk_tools.py`

```python
# New guard at tool execution entry
MUTATING_TOOL_TYPES = {
    "Create Document", "Create Multiple Documents",
    "Update Document", "Update Multiple Documents", 
    "Delete Document", "Delete Multiple Documents",
    "Submit Document", "Cancel Document",
    "Set Value", "POST", "Run Agent"
}

def _check_tool_permission(tool_type: str, context: dict = None):
    """Guard function to block dangerous tools for Guest users"""
    user = frappe.session.user
    
    # Hard block: Guest cannot use mutating tools
    if user == "Guest" and tool_type in MUTATING_TOOL_TYPES:
        return {
            "allowed": False,
            "error": f"Guest users cannot use {tool_type} tools. Please log in."
        }
    
    return {"allowed": True}
```

**Apply in `on_invoke_tool` wrapper:**

```python
async def on_invoke_tool(ctx=None, args_json: str = None) -> str:
    # NEW: Permission check before execution
    perm_check = _check_tool_permission(tool_type, ctx)
    if not perm_check["allowed"]:
        return json.dumps({"error": perm_check["error"], "denied": True})
    
    # Continue with existing logic...
```

### Priority 2: Enforce frappe.has_permission in CRUD Tools

**Implementation Location**: `huf/ai/tool_functions.py`

```python
def create_document(doctype: str, data: dict, function=None):
    """Create a document with explicit permission check"""
    
    # NEW: Pre-check permission
    if not frappe.has_permission(doctype, "create"):
        return {
            "success": False,
            "error": f"You do not have permission to create {doctype}",
            "permission_denied": True
        }
    
    # Existing logic...
    doc = frappe.get_doc({"doctype": doctype, **data})
    doc.insert()
    return {"document_id": doc.name, "message": "Document created", "doctype": doctype}


def update_document(doctype: str, document_id: str, data: dict, tool=None):
    """Update a document with explicit permission check"""
    
    # NEW: Pre-check write permission
    if not frappe.db.exists(doctype, document_id):
        return {"success": False, "error": f"{doctype} {document_id} not found"}
    
    if not frappe.has_permission(doctype, "write", doc=document_id):
        return {
            "success": False,
            "error": f"You do not have write permission on {doctype} {document_id}",
            "permission_denied": True
        }
    
    # Existing logic...


def delete_document(doctype: str, document_id: str):
    """Delete a document with explicit permission check"""
    
    # NEW: Pre-check delete permission
    if not frappe.has_permission(doctype, "delete", doc=document_id):
        return {
            "success": False,
            "error": f"You do not have delete permission on {doctype} {document_id}",
            "permission_denied": True
        }
    
    # Existing logic...


def submit_document(doctype: str, document_id: str):
    """Submit a document with explicit permission check"""
    
    # NEW: Pre-check submit permission
    if not frappe.has_permission(doctype, "submit", doc=document_id):
        return {
            "success": False,
            "error": f"You do not have submit permission on {doctype} {document_id}",
            "permission_denied": True
        }
    
    # Existing logic...
```

### Priority 3: Bind Execution to Session User

**Implementation Location**: `huf/ai/agent_integration.py`

```python
@frappe.whitelist(allow_guest=True)
def run_agent_sync(agent_name, prompt, ...):
    # NEW: Capture and validate acting user at entry
    acting_user = frappe.session.user
    
    # Validate against Agent's allowed_users/allowed_roles
    agent_doc = frappe.get_doc("Agent", agent_name)
    
    if not _is_user_allowed(agent_doc, acting_user):
        frappe.throw(
            _("You are not authorized to use this agent."),
            frappe.PermissionError
        )
    
    # Pass acting_user through context for audit
    context = {
        "acting_user": acting_user,
        "channel": channel_id,
        ...
    }
```

**Helper function:**

```python
def _is_user_allowed(agent_doc, user: str) -> bool:
    """Check if user is allowed to run this agent"""
    
    # Guest check
    if user == "Guest":
        return agent_doc.allow_guest
    
    # Check allowed_users if specified
    if agent_doc.allowed_users:
        allowed_user_names = [u.user for u in agent_doc.allowed_users]
        if user in allowed_user_names:
            return True
    
    # Check allowed_roles if specified  
    if agent_doc.allowed_roles:
        allowed_role_names = [r.role for r in agent_doc.allowed_roles]
        user_roles = frappe.get_roles(user)
        if any(role in user_roles for role in allowed_role_names):
            return True
    
    # If no restrictions specified, allow all logged-in users
    if not agent_doc.allowed_users and not agent_doc.allowed_roles:
        return True
    
    return False
```

---

## Medium-term Improvements

### 1. Introduce Execution Identity (First-class Concept)

Add new fields to Agent DocType:

```json
{
    "fieldname": "execution_mode",
    "fieldtype": "Select",
    "label": "Execution Mode",
    "options": "session_user\nfixed_user\nservice_role",
    "default": "session_user",
    "description": "How the agent's identity is determined during execution"
},
{
    "fieldname": "fixed_execution_user", 
    "fieldtype": "Link",
    "options": "User",
    "label": "Fixed Execution User",
    "depends_on": "eval:doc.execution_mode=='fixed_user'",
    "description": "User to execute as when mode is fixed_user"
},
{
    "fieldname": "service_role",
    "fieldtype": "Link", 
    "options": "Role",
    "label": "Service Role",
    "depends_on": "eval:doc.execution_mode=='service_role'",
    "description": "Role to use for permission checks in service_role mode"
}
```

**Execution Mode Options:**

| Mode | Meaning | Use Case |
|------|---------|----------|
| `session_user` | Acts as the calling user | Chat, Portal, Desk |
| `fixed_user` | Always acts as specified user | Service accounts, bots |
| `service_role` | Uses predefined system role | Read-only bots, ops automation |

### 2. Permission-Aware Tool Registry

Create a tool registry that filters tools based on user permissions:

```python
# New file: huf/ai/tool_registry.py

class PermissionAwareToolRegistry:
    """Registry that filters tools based on user permissions"""
    
    TOOL_PERMISSIONS = {
        "Get Document": {"permission": "read", "level": "doctype"},
        "Get List": {"permission": "read", "level": "doctype"},
        "Create Document": {"permission": "create", "level": "doctype"},
        "Update Document": {"permission": "write", "level": "doctype"},
        "Delete Document": {"permission": "delete", "level": "doctype"},
        "Submit Document": {"permission": "submit", "level": "doctype"},
        "Cancel Document": {"permission": "cancel", "level": "doctype"},
    }
    
    @classmethod
    def get_allowed_tools(cls, agent_doc, user: str) -> list:
        """Return only tools the user has permission to use"""
        all_tools = []
        
        for tool_link in agent_doc.agent_tool:
            tool_doc = frappe.get_doc("Agent Tool Function", tool_link.tool)
            
            # Check if user can use this tool type
            if cls._can_use_tool(tool_doc, user):
                all_tools.append(tool_doc)
        
        return all_tools
    
    @classmethod
    def _can_use_tool(cls, tool_doc, user: str) -> bool:
        """Check if user has permission for this tool"""
        tool_type = tool_doc.types
        
        # Guest restrictions
        if user == "Guest" and tool_type in MUTATING_TOOL_TYPES:
            return False
        
        # DocType-specific permission check
        if tool_doc.reference_doctype:
            perm_info = cls.TOOL_PERMISSIONS.get(tool_type, {})
            perm_type = perm_info.get("permission")
            
            if perm_type and not frappe.has_permission(
                tool_doc.reference_doctype, 
                perm_type
            ):
                return False
        
        return True
```

### 3. Three-Layer Guardrails

Implement defense in depth with three layers of protection:

```
┌─────────────────────────────────────────────────────┐
│                    LAYER 1: UI                       │
│  - Guest chat → no mutating intent suggested        │
│  - Tool suggestions based on user role              │
│  - Clear permission messaging in UI                 │
└─────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────┐
│                  LAYER 2: AGENT                      │
│  - Tools filtered by user permissions               │
│  - Agent never sees tools user can't use            │
│  - Execution identity explicitly bound              │
└─────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────┐
│                   LAYER 3: TOOL                      │
│  - Final permission check (last line of defense)    │
│  - Explicit has_permission() call                   │
│  - Structured error response for denied actions     │
└─────────────────────────────────────────────────────┘
```

---

## Long-term Security Model

### Execution Identity Architecture

```python
class ExecutionIdentity:
    """
    First-class identity for agent execution.
    Every agent run MUST have one and only one identity.
    """
    
    def __init__(self, agent_doc, triggering_user: str):
        self.mode = agent_doc.execution_mode
        self.triggering_user = triggering_user
        self.effective_user = self._resolve_effective_user(agent_doc)
        self.effective_roles = self._resolve_effective_roles(agent_doc)
    
    def _resolve_effective_user(self, agent_doc) -> str:
        if self.mode == "session_user":
            return self.triggering_user
        elif self.mode == "fixed_user":
            return agent_doc.fixed_execution_user
        elif self.mode == "service_role":
            return "service_account"  # Special system user
        return self.triggering_user
    
    def _resolve_effective_roles(self, agent_doc) -> list:
        if self.mode == "service_role":
            return [agent_doc.service_role]
        return frappe.get_roles(self.effective_user)
    
    def has_permission(self, doctype: str, ptype: str, doc=None) -> bool:
        """Check permission using effective identity"""
        if self.mode == "service_role":
            # Check role-based permission
            return self._check_role_permission(doctype, ptype)
        else:
            # Use Frappe's standard permission check
            return frappe.has_permission(
                doctype, ptype, doc, 
                user=self.effective_user
            )
    
    def to_audit_dict(self) -> dict:
        """Return identity info for audit logging"""
        return {
            "mode": self.mode,
            "triggering_user": self.triggering_user,
            "effective_user": self.effective_user,
            "effective_roles": self.effective_roles
        }
```

### Agent Tool Function Enhancement

Add permission metadata to tools:

```json
{
    "fieldname": "required_permission",
    "fieldtype": "Select",
    "label": "Required Permission",
    "options": "read\nwrite\ncreate\ndelete\nsubmit\ncancel",
    "description": "Permission level required to use this tool"
},
{
    "fieldname": "is_read_only",
    "fieldtype": "Check",
    "label": "Read Only",
    "default": 0,
    "description": "If checked, this tool does not modify data"
},
{
    "fieldname": "allowed_for_guest",
    "fieldtype": "Check", 
    "label": "Allowed for Guest",
    "default": 0,
    "description": "If checked, Guest users can use this tool"
}
```

---

## Implementation by Component

### DocTypes (CRUD Operations)

| Immediate | Medium-term | Long-term |
|-----------|-------------|-----------|
| Add explicit `has_permission()` before every CRUD | Filter tools at agent load time | Use ExecutionIdentity for all checks |
| Return structured errors on denial | Tool permission metadata | Audit logging with identity |
| Block Guest from mutating tools | Permission-aware tool suggestions | Role-based tool access |

### MCP Tools

| Immediate | Medium-term | Long-term |
|-----------|-------------|-----------|
| Add permission check before MCP execution | MCP server-level permission config | MCP tool permission inheritance |
| Block Guest from all MCP tools | Tool-level whitelist per role | Federated identity to MCP |
| Log all MCP tool executions | Rate limiting per user | MCP server authentication flow |

### HTTP Tools (GET/POST)

| Immediate | Medium-term | Long-term |
|-----------|-------------|-----------|
| Enforce SSRF validation (already done) | URL whitelist per agent | OAuth flow for external APIs |
| Block Guest from POST requests | Header sanitization | External API credential management |
| Add request logging | Response validation | API gateway integration |

### Custom Functions

| Immediate | Medium-term | Long-term |
|-----------|-------------|-----------|
| Document permission requirements | Decorator for permission check | Auto-generate permission checks |
| Add @frappe.whitelist checks | Sandbox execution environment | Static analysis for security |
| Validate function_path at save | Function audit logging | Capability-based security |

---

## Security Checklist

### Before Deployment

- [ ] Guest users cannot use mutating tools
- [ ] All CRUD tools have explicit permission checks
- [ ] `allowed_users`/`allowed_roles` are enforced
- [ ] MCP tools respect user permissions
- [ ] Audit logging captures execution identity
- [ ] Error messages don't leak sensitive info

### Agent Configuration Review

- [ ] Review all agents with `allow_guest=True`
- [ ] Verify `allowed_users`/`allowed_roles` are set appropriately
- [ ] Review custom functions for security vulnerabilities
- [ ] Check MCP server permissions and tool exposure

### Runtime Monitoring

- [ ] Monitor for Guest tool execution attempts
- [ ] Alert on permission denied patterns
- [ ] Track MCP tool usage by user
- [ ] Audit trail for sensitive operations

---

## Migration Path

### Phase 1: Immediate Hardening (1-2 weeks)
1. Implement Guest tool blocking
2. Add explicit permission checks to CRUD tools
3. Enforce `allowed_users`/`allowed_roles`
4. Add audit logging for tool execution

### Phase 2: Permission-Aware Tools (3-4 weeks)
1. Add tool permission metadata
2. Implement tool filtering at agent load
3. Create permission-aware tool registry
4. Update UI to show allowed tools only

### Phase 3: Execution Identity (6-8 weeks)
1. Implement ExecutionIdentity class
2. Add execution_mode to Agent DocType
3. Update all tool execution to use identity
4. Create audit dashboard

### Phase 4: Advanced Security (Ongoing)
1. MCP tool permission inheritance
2. OAuth for external APIs
3. Capability-based security model
4. Security compliance reporting

---

## Appendix: Code References

### Files to Modify

| File | Changes |
|------|---------|
| `huf/ai/tool_functions.py` | Add permission checks to all CRUD functions |
| `huf/ai/sdk_tools.py` | Add permission filtering, Guest blocking |
| `huf/ai/agent_integration.py` | Enforce allowed_users/roles, pass identity |
| `huf/ai/mcp_client.py` | Add permission checks before MCP execution |
| `huf/huf/doctype/agent/agent.json` | Add execution_mode fields |
| `huf/huf/doctype/agent_tool_function/agent_tool_function.json` | Add permission metadata |

### New Files to Create

| File | Purpose |
|------|---------|
| `huf/ai/security/execution_identity.py` | ExecutionIdentity class |
| `huf/ai/security/tool_registry.py` | Permission-aware tool registry |
| `huf/ai/security/guards.py` | Permission guard functions |
| `huf/ai/security/audit.py` | Security audit logging |

---

## Summary

The HUF agent system currently has significant security gaps that allow:
1. Guest users to execute mutating operations
2. Tools to execute without explicit permission validation
3. No clear execution identity binding
4. Underutilized permission configuration fields

This document provides a three-phase approach:
- **Immediate**: Block critical vulnerabilities
- **Medium-term**: Build permission-aware infrastructure  
- **Long-term**: Implement proper execution identity model

The key principle remains: **Agents don't have power. Users have power. Agents only borrow it — explicitly.**
