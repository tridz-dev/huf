# OpenSandbox Integration into HUF

> **Branch**: `claude/integrate-opensandbox-4kgCC`
> **Date**: 2026-03-18
> **Status**: Design / Planning

---

## 1. Why This Integration Matters

HUF agents currently execute Python code in two unsafe ways:

| Current Path | Risk |
|---|---|
| `Custom Function` tool type — dynamically imports and calls any `@frappe.whitelist()` function | Full Python execution on the Frappe server with zero isolation |
| `App Provided` tool type — same mechanism via `get_function_from_name()` in `sdk_tools.py` | Same — no sandboxing |

**OpenSandbox** provides an isolated Docker/Kubernetes environment where arbitrary code (Python, shell, etc.) can run without touching the Frappe process. Adding it to HUF enables:

- **Code Interpreter tools** — agents write + run Python, get structured output back
- **Shell command tools** — agents run bash commands in a contained environment
- **Safe custom function execution** — move risky custom code out of the Frappe process
- **Data analysis / ML workloads** — agents can do pandas, matplotlib, sklearn inside a sandbox
- **Agent Evaluation** — run test scripts against agent outputs in isolation

---

## 2. How OpenSandbox Works (Relevant Subset)

```
┌─────────────────────────────────────────────────────────┐
│  OpenSandbox Server  (FastAPI, runs separately)          │
│  Config: ~/.sandbox.toml                                 │
│                                                          │
│  ┌─────────────────┐    ┌─────────────────────────────┐  │
│  │  Lifecycle API  │    │  Execution Daemon (execd)   │  │
│  │  POST /sandbox  │    │  commands.run()             │  │
│  │  GET  /sandbox  │    │  files.read/write()         │  │
│  │  DELETE /sandbox│    │  code_interpreter.run()     │  │
│  └────────┬────────┘    └─────────────────────────────┘  │
│           │ Docker / Kubernetes                           │
└───────────┼─────────────────────────────────────────────┘
            │ Python SDK (async)
┌───────────▼─────────────────────────────────────────────┐
│  HUF Frappe Server (this codebase)                       │
│                                                          │
│  huf/ai/opensandbox_tool.py  ← new file                  │
│  Agent Tool Function (new type: "Run in Sandbox")        │
│  Sandbox Config DocType       ← new doctype              │
└─────────────────────────────────────────────────────────┘
```

**Python SDK quick reference:**

```python
from opensandbox import Sandbox
from code_interpreter import CodeInterpreter, SupportedLanguage

# Create a sandbox (Docker image, timeout, env vars)
sandbox = await Sandbox.create(
    "opensandbox/code-interpreter:v1.0.2",
    timeout=timedelta(minutes=10),
    env={"PYTHON_VERSION": "3.11"},
)

async with sandbox:
    # Run shell commands
    result = await sandbox.commands.run("ls -la /tmp")

    # Read / write files
    await sandbox.files.write_files([WriteEntry(path="/tmp/data.csv", data=csv_string)])
    content = await sandbox.files.read_file("/tmp/output.txt")

    # Execute Python code and get structured output
    interpreter = await CodeInterpreter.create(sandbox)
    output = await interpreter.codes.run(code, language=SupportedLanguage.PYTHON)
    print(output.result[0].text)   # last expression value
    print(output.logs.stdout[0].text)  # stdout
```

---

## 3. Integration Approaches

Three approaches are viable, ranked by scope/effort:

### Approach A — New Tool Type: "Run in Sandbox" ⭐ Recommended

Add a new `Agent Tool Function` type called `"Run in Sandbox"`. When an agent invokes this tool, HUF:

1. Opens a connection to the configured OpenSandbox server
2. Creates an ephemeral sandbox with a specified Docker image
3. Optionally uploads input files/data to the sandbox
4. Executes the code or command the LLM provided
5. Returns stdout, result, files, and errors back to the agent
6. Kills the sandbox

This fits naturally into HUF's existing tool dispatch in `sdk_tools.py` — add a new `elif tool_type == "Run in Sandbox"` branch that returns a `FunctionTool` backed by the OpenSandbox Python SDK.

**Pros**: Minimal invasiveness, reuses all existing tool UI, works with flow engine, scheduling, chat, doc events
**Cons**: Requires OpenSandbox server to be deployed and reachable from the Frappe host

---

### Approach B — Sandbox-Backed Custom Function Execution

Replace the unsafe `get_function_from_name()` path with optional sandboxed execution. When a `Custom Function` tool has `run_in_sandbox: true`, send the function source code to an OpenSandbox code-interpreter instead of importing it in-process.

**Pros**: Makes existing Custom Function tools safer without changing agent configuration
**Cons**: Complex — need to serialize the function, its imports, and dependencies into the sandbox; Frappe context won't be available inside the sandbox

---

### Approach C — Full Code Interpreter Chat Capability

Add a `code_interpreter_enabled` flag on the `Agent` DocType. When enabled, every agent conversation gets an attached long-lived sandbox session. The agent can freely write and execute code across multiple turns, with the sandbox persisting for the duration of the conversation.

**Pros**: Full ChatGPT-style code interpreter experience
**Cons**: Most complex — requires sandbox session lifecycle tied to `Agent Conversation`, significant new state management

---

## 4. Detailed Implementation Plan (Approach A)

### 4.1 New DocType: `Sandbox Config`

Stores the connection parameters for the OpenSandbox server. Singleton (like `Agent Settings`).

```
Sandbox Config
├── sandbox_server_url      Data       "http://localhost:8001"
├── api_key                 Password   (optional auth)
├── default_image           Data       "opensandbox/code-interpreter:v1.0.2"
├── default_timeout_minutes Int        10
├── max_timeout_minutes     Int        30
├── enabled                 Check      (global on/off switch)
└── section: Resource Limits
    ├── max_cpu             Data       "1.0"
    └── max_memory          Data       "512m"
```

**File**: `huf/huf/doctype/sandbox_config/sandbox_config.py`

---

### 4.2 New Tool Type Constant

**File**: `huf/huf/doctype/agent_tool_type/agent_tool_type.json` (or wherever tool types are enumerated)

Add `"Run in Sandbox"` to the tool type select options.

Also in `huf/ai/tool_registry.py`:

```python
# Run in Sandbox is non-mutating from Frappe's perspective
# (it doesn't touch Frappe DB), so it's safe for guest... or not:
# decide based on policy. Recommend: require login.
```

---

### 4.3 New Agent Tool Function Fields

When `types == "Run in Sandbox"`, the `Agent Tool Function` DocType needs additional fields:

```
Agent Tool Function (additions)
├── sandbox_image           Data    (override default image per tool)
├── sandbox_entrypoint      Code    (custom entrypoint command)
├── sandbox_env_vars        Table   → SandboxEnvVar child doctype
│   ├── key                 Data
│   └── value               Data
├── execution_mode          Select  ["python_code", "shell_command", "code_interpreter"]
├── code_template           Code    (optional static code wrapping LLM output)
└── allow_file_output       Check   (whether to capture output files)
```

---

### 4.4 New File: `huf/ai/opensandbox_tool.py`

This module provides the `create_sandbox_tool()` function that `sdk_tools.py` calls.

```python
"""
OpenSandbox tool integration for HUF.

Creates FunctionTool instances backed by isolated OpenSandbox containers.
"""
import asyncio
import json
from datetime import timedelta
from typing import Any

import frappe
from agents import FunctionTool


def get_sandbox_config() -> dict:
    """Fetch and validate Sandbox Config singleton."""
    try:
        config = frappe.get_single("Sandbox Config")
    except Exception:
        frappe.throw("Sandbox Config not found. Please configure it in HUF Settings.")
    if not config.enabled:
        frappe.throw("Sandbox execution is disabled. Enable it in Sandbox Config.")
    return config


def create_sandbox_tool(function_doc) -> FunctionTool:
    """
    Returns a FunctionTool that executes code/commands inside an OpenSandbox.

    Called from sdk_tools.create_agent_tools() when tool type is "Run in Sandbox".
    """
    config = get_sandbox_config()
    tool_name = function_doc.tool_name
    description = function_doc.description or f"Execute code in an isolated sandbox: {tool_name}"
    execution_mode = function_doc.execution_mode or "python_code"
    sandbox_image = function_doc.sandbox_image or config.default_image
    timeout_minutes = min(
        int(config.default_timeout_minutes or 10),
        int(config.max_timeout_minutes or 30),
    )

    # Collect static env vars from the tool doc
    static_env = {}
    if hasattr(function_doc, "sandbox_env_vars") and function_doc.sandbox_env_vars:
        for row in function_doc.sandbox_env_vars:
            static_env[row.key] = row.value

    async def on_invoke(ctx, args_json: str) -> str:
        try:
            args = json.loads(args_json)
        except json.JSONDecodeError:
            return json.dumps({"error": "Invalid JSON arguments"})

        code_or_command = args.get("code") or args.get("command") or ""
        if not code_or_command.strip():
            return json.dumps({"error": "No code or command provided"})

        try:
            from opensandbox import Sandbox
            from opensandbox.models import ConnectionConfig
        except ImportError:
            return json.dumps({
                "error": "opensandbox package not installed. Run: pip install opensandbox"
            })

        connection_config = ConnectionConfig(
            domain=config.sandbox_server_url,
            api_key=config.get_password("api_key") if config.api_key else None,
        )

        try:
            sandbox = await Sandbox.create(
                sandbox_image,
                timeout=timedelta(minutes=timeout_minutes),
                env=static_env or None,
                connection_config=connection_config,
            )
        except Exception as e:
            frappe.log_error(f"Sandbox creation failed: {e}", "OpenSandbox Error")
            return json.dumps({"error": f"Sandbox creation failed: {str(e)}"})

        try:
            async with sandbox:
                if execution_mode == "shell_command":
                    result = await sandbox.commands.run(code_or_command)
                    return json.dumps({
                        "stdout": "".join(l.text for l in result.logs.stdout),
                        "stderr": "".join(l.text for l in result.logs.stderr),
                        "exit_code": result.exit_code,
                    })

                elif execution_mode == "python_code":
                    # Write code to a file and execute it
                    from opensandbox.models import WriteEntry
                    await sandbox.files.write_files([
                        WriteEntry(path="/tmp/huf_script.py", data=code_or_command, mode=644)
                    ])
                    result = await sandbox.commands.run("python3 /tmp/huf_script.py")
                    return json.dumps({
                        "stdout": "".join(l.text for l in result.logs.stdout),
                        "stderr": "".join(l.text for l in result.logs.stderr),
                        "exit_code": result.exit_code,
                    })

                elif execution_mode == "code_interpreter":
                    from code_interpreter import CodeInterpreter, SupportedLanguage
                    interpreter = await CodeInterpreter.create(sandbox)
                    output = await interpreter.codes.run(
                        code_or_command,
                        language=SupportedLanguage.PYTHON,
                    )
                    result_text = output.result[0].text if output.result else ""
                    stdout = "".join(l.text for l in output.logs.stdout)
                    stderr = "".join(l.text for l in output.logs.stderr)
                    return json.dumps({
                        "result": result_text,
                        "stdout": stdout,
                        "stderr": stderr,
                    })

                else:
                    return json.dumps({"error": f"Unknown execution_mode: {execution_mode}"})

        except Exception as e:
            frappe.log_error(f"Sandbox execution error: {e}", "OpenSandbox Error")
            return json.dumps({"error": f"Execution failed: {str(e)}"})
        finally:
            try:
                await sandbox.kill()
            except Exception:
                pass  # Best-effort cleanup

    # Build the tool schema the LLM sees
    if execution_mode == "shell_command":
        input_schema = {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute in the sandbox",
                }
            },
            "required": ["command"],
        }
    else:
        input_schema = {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "The Python code to execute in the isolated sandbox",
                }
            },
            "required": ["code"],
        }

    return FunctionTool(
        name=tool_name,
        description=description,
        params_json_schema=input_schema,
        on_invoke_tool=on_invoke,
    )
```

---

### 4.5 Wire Into `sdk_tools.py`

In `huf/ai/sdk_tools.py`, find the tool type dispatch loop (around line 75–200) and add:

```python
elif function_doc.types == "Run in Sandbox":
    from huf.ai.opensandbox_tool import create_sandbox_tool
    tool = create_sandbox_tool(function_doc)
    if tool:
        tools.append(tool)
```

This sits alongside the existing `elif` branches for `"Custom Function"`, `"MCP Tool"`, `"Client Side Tool"`, etc.

---

### 4.6 Dependency: Add `opensandbox` to `pyproject.toml`

```toml
[project.dependencies]
# ... existing deps ...
opensandbox = ">=0.1.0"
opensandbox-code-interpreter = ">=0.1.0"  # only if code_interpreter mode used
```

The install will happen automatically via `bench setup requirements`.

---

### 4.7 Frontend Changes

**`src/data/doctypes.ts`** — add the new DocType constant:

```typescript
sandboxConfig: "Sandbox Config",
```

**Agent Tool Function form** — in `components/agent/ToolsTab` (or wherever the tool form renders), show sandbox-specific fields when type is `"Run in Sandbox"`:

- Sandbox Image (text input with default placeholder)
- Execution Mode (select: Python Code | Shell Command | Code Interpreter)
- Environment Variables (key-value table)
- Timeout Override (number input)

This follows the same conditional field pattern already used for HTTP headers (shown when type is `"GET Request"` or `"POST Request"`).

---

## 5. Long-Lived Sandbox Sessions (Approach C — Future)

For a full code-interpreter experience tied to a conversation:

```
Agent Conversation
└── sandbox_id    Data    (FK to active sandbox)
```

On conversation start → `Sandbox.create()`, store the `sandbox.id`.
On subsequent turns → `Sandbox.connect(sandbox_id)`.
On conversation end / timeout → `sandbox.kill()`.

This enables stateful execution (variables persist across messages, files stay available). Adds complexity:
- Need a background job or webhook to kill orphaned sandboxes
- `sandbox_id` must be managed in `conversation_manager.py`
- The `run_agent_stream()` path needs async cooperation with the sandbox session

---

## 6. Architecture Fit

```
HUF Agent Execution Flow (with OpenSandbox)
════════════════════════════════════════════

User Prompt
    │
    ▼
AgentManager.run_agent_sync() / run_agent_stream()
    │  (agent_integration.py)
    │
    ▼
openai-agents SDK calls LLM
    │
    ◄── LLM decides to call "Run in Sandbox" tool
    │
    ▼
sdk_tools.py → create_agent_tools() → create_sandbox_tool()
    │
    ▼
opensandbox_tool.py → on_invoke()
    │
    ├──► Sandbox.create()  ──► OpenSandbox Server  ──► Docker container
    │
    ├──► commands.run() / codes.run()
    │
    ├──► collect stdout / result
    │
    └──► sandbox.kill()
    │
    ▼
Return JSON result to LLM
    │
    ▼
LLM produces final response → user
```

The sandbox call is **async** (`on_invoke_tool` is already `async` in HUF's `FunctionTool` pattern). The `asyncio.run()` wrapping HUF uses for sync execution will carry this through correctly.

---

## 7. Deployment Prerequisites

| Component | Requirement |
|---|---|
| OpenSandbox Server | Docker host reachable from the Frappe server. Can be same machine or separate. Run `uv pip install opensandbox-server && opensandbox-server` |
| Docker | Required on the machine running OpenSandbox Server |
| Python package | `opensandbox` (and optionally `opensandbox-code-interpreter`) installed in the Frappe virtualenv |
| Network | Frappe → OpenSandbox Server HTTP/HTTPS. OpenSandbox → Docker socket. |
| Sandbox images | Pre-pulled images e.g. `docker pull opensandbox/code-interpreter:v1.0.2` |

### Docker-based HUF

The existing `docker/docker-compose.yml` can be extended with an `opensandbox` service:

```yaml
services:
  opensandbox:
    image: opensandbox-server:latest   # or build from source
    ports:
      - "8001:8001"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock  # sandbox server needs Docker socket
    environment:
      - SANDBOX_CONFIG=/app/config.toml
```

Then `sandbox_server_url` in `Sandbox Config` = `http://opensandbox:8001`.

---

## 8. Security Considerations

### What OpenSandbox Fixes

| Current Risk | OpenSandbox Mitigation |
|---|---|
| Custom Python code runs in Frappe process | Code runs in isolated Docker container, no Frappe DB access |
| No resource limits on custom code | CPU/memory limits enforced by Docker cgroup |
| Long-running code blocks Frappe worker | Sandbox timeout kills the container automatically |
| Filesystem access from custom code | Sandbox has its own filesystem, ephemeral by default |

### Remaining / New Risks

| Risk | Notes |
|---|---|
| **LLM-generated code execution** | The LLM writes the code that runs in the sandbox. Prompt injection could cause malicious code. Mitigate with network egress controls (OpenSandbox's egress component blocks outbound requests by default). |
| **OpenSandbox server exposure** | If accessible from outside the network, it becomes an RCE endpoint. Bind to localhost or internal network only. Add API key auth via `Sandbox Config`. |
| **Docker socket access** | OpenSandbox server needs `docker.sock`. This is a high-privilege path — run the sandbox server as a non-root user or use rootless Docker. |
| **Container escape** | Standard Docker isolation. For higher security, configure gVisor or Firecracker (OpenSandbox supports both via `secureRuntime` config). |
| **Data exfiltration via code** | Sandbox egress should block all outbound traffic by default. Use OpenSandbox's egress component to define allowlists. |
| **Sensitive data passed to sandbox** | HUF agents might pass Frappe document data into sandbox code. Ensure sensitive fields are not passed unless necessary. |
| **Sandbox timeout denial-of-service** | Many agents calling long-running sandboxes could exhaust Docker resources. Enforce `max_timeout_minutes` in `Sandbox Config` and add a concurrency limit. |
| **Image supply chain** | Only use trusted images (Alibaba's official `opensandbox/*` or internally built). Pin image digests, not just tags. |

### Recommended Security Configuration

```toml
# ~/.sandbox.toml (OpenSandbox server config)
[sandbox]
max_cpu = "1.0"
max_memory = "512m"
network_policy = "block_all_egress"     # no outbound from sandbox
max_lifetime_minutes = 15               # hard cap
```

---

## 9. Step-by-Step Implementation

```
Phase 1: Infrastructure (no code changes in HUF)
─────────────────────────────────────────────────
□ Deploy OpenSandbox Server alongside HUF (Docker Compose or standalone)
□ Verify it's reachable: curl http://localhost:8001/health
□ Pull the code-interpreter image: docker pull opensandbox/code-interpreter:v1.0.2
□ Test Python SDK manually (see examples above)

Phase 2: Backend (HUF changes)
─────────────────────────────────────────────────
□ Add opensandbox dependency to pyproject.toml
□ Create Sandbox Config DocType (JSON + Python controller)
□ Add "Run in Sandbox" to agent_tool_type select options
□ Add sandbox-specific fields to agent_tool_function DocType
□ Create huf/ai/opensandbox_tool.py
□ Wire into sdk_tools.py dispatch loop
□ Add SandboxEnvVar child DocType for per-tool env vars
□ Run bench migrate to apply schema changes

Phase 3: Frontend
─────────────────────────────────────────────────
□ Add SandboxConfig DocType constant to src/data/doctypes.ts
□ Add sandbox field section to Agent Tool Function form
  (conditional on type == "Run in Sandbox")
□ Add Sandbox Config page to Settings area (or embed in Agent Settings)

Phase 4: Testing
─────────────────────────────────────────────────
□ Unit test: create_sandbox_tool() returns valid FunctionTool
□ Integration test: agent with "Run in Sandbox" tool executes Python
□ Security test: sandbox cannot access Frappe DB
□ Timeout test: verify sandbox is killed after timeout
□ Error path: OpenSandbox server down → graceful error in agent response
```

---

## 10. Example Agent Configuration After Integration

**Agent**: "Data Analyst"
**Tools**:
- `analyze_data` — type: `Run in Sandbox`, execution_mode: `code_interpreter`, image: `opensandbox/code-interpreter:v1.0.2`
- `get_report_data` — type: `Get Report` (existing HUF tool, fetches Frappe report)

**Flow**:
1. Agent calls `get_report_data("Monthly Sales")` → gets JSON data from Frappe
2. Agent calls `analyze_data(code="import pandas as pd\n...")` passing the data
3. Code runs in isolated Docker container, returns `{"result": "42.5", "stdout": "..."}`
4. Agent interprets result and responds to user

This is the same pattern as ChatGPT's Advanced Data Analysis — but running on your own Frappe data, with your own LLM, in your own infrastructure.

---

## 11. Alternative: MCP-Based Integration

OpenSandbox's sandbox-as-a-tool pattern could also be exposed as an MCP server. A thin MCP wrapper around the OpenSandbox Python SDK could serve tools like `run_python`, `run_shell`, `read_file`, `write_file`.

HUF already supports MCP servers (via `MCP Server` DocType and `mcp_client.py`). This would require:
1. Build a small MCP server wrapping OpenSandbox (outside HUF)
2. Register it in HUF's `MCP Server` DocType
3. Agents pick it up automatically via existing MCP tool loading

**Trade-off**: Requires maintaining a separate MCP server process. Approach A (direct SDK) is simpler for HUF's deployment model.

---

## 12. Effort Estimate

| Phase | Effort | Notes |
|---|---|---|
| Infrastructure (Phase 1) | 0.5 days | Mostly Docker Compose config |
| Sandbox Config DocType | 0.5 days | JSON schema + controller |
| `opensandbox_tool.py` | 1 day | Core logic, async handling, error paths |
| `sdk_tools.py` wiring | 0.5 days | One `elif` branch + tests |
| Frontend tool form fields | 1 day | Conditional fields for sandbox config |
| Testing + docs | 1 day | |
| **Total (Approach A)** | **~4.5 days** | |
| + Long-lived sessions (Approach C) | +3 days | If desired later |
