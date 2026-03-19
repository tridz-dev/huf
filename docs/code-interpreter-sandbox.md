# Code Interpreter & Sandbox Network Policy

The **Code Interpreter** tool type lets an AI agent execute code inside a sandboxed environment. A configurable **network policy** controls whether the sandbox can reach the internet — and if so, which domains are allowed.

---

## Table of Contents

- [Overview](#overview)
- [Network Policy Modes](#network-policy-modes)
- [Creating a Code Interpreter Tool](#creating-a-code-interpreter-tool)
- [Wiring a Sandbox Runtime](#wiring-a-sandbox-runtime)
- [Deployment Scenarios](#deployment-scenarios)
  - [Scenario A — Local Bench + Local Docker](#scenario-a--local-bench--local-docker)
  - [Scenario B — HUF in Docker + Host Docker Engine](#scenario-b--huf-in-docker--host-docker-engine)
  - [Scenario C — Remote VPS (DigitalOcean / Hetzner / AWS)](#scenario-c--remote-vps-digitalocean--hetzner--aws)
- [Testing the Integration](#testing-the-integration)
- [Security Notes](#security-notes)
- [API Reference](#api-reference)

---

## Overview

When an agent has a Code Interpreter tool attached, the LLM can emit tool calls like:

```json
{
  "code": "import pandas as pd\ndf = pd.read_csv('data.csv')\nprint(df.describe())",
  "language": "python",
  "timeout": 30
}
```

HUF builds a `NetworkPolicy` from the tool's configuration, converts it to a `sandbox_config` dict, and passes both the code and the config to the sandbox runtime.

```
Agent  ──tool_call──▶  sdk_tools.py  ──sandbox_config──▶  Sandbox Runtime
                            │                                    │
                    NetworkPolicy.from_tool_doc()          executes code
                            │                              enforces network
                    to_sandbox_config()                         │
                            │                              returns stdout/stderr
                            ▼                                    │
                    { "network": "whitelist",              ◀─────┘
                      "allowed_domains": [...] }
```

---

## Network Policy Modes

| Mode | Outbound Network | Use When |
|------|-----------------|----------|
| **Disabled** | Fully blocked — no DNS, no TCP | Code only processes data already available; maximum security |
| **Whitelist** | Only listed domains reachable | Code needs to `pip install`, `npm install`, or call specific APIs |
| **Open** | Unrestricted | Code is fully trusted, or you need arbitrary web access |

### Presets (Whitelist mode)

Toggle one or more package-manager presets to auto-allow their registry domains:

| Preset | Allowed Domains |
|--------|----------------|
| `npm` | `registry.npmjs.org`, `registry.yarnpkg.com`, `npmjs.org` |
| `pip` | `pypi.org`, `files.pythonhosted.org`, `pypi.python.org` |
| `apt` | `archive.ubuntu.com`, `security.ubuntu.com`, `deb.debian.org`, `ports.ubuntu.com`, `ppa.launchpad.net` |
| `brew` | `formulae.brew.sh`, `raw.githubusercontent.com`, `objects.githubusercontent.com`, `github.com`, `api.github.com` |
| `docker` | `registry-1.docker.io`, `auth.docker.io`, `production.cloudflare.docker.com`, `index.docker.io` |
| `cargo` | `crates.io`, `static.crates.io`, `index.crates.io` |
| `gem` | `rubygems.org`, `api.rubygems.org`, `gems.rubygems.org` |
| `go` | `proxy.golang.org`, `sum.golang.org`, `pkg.go.dev` |
| `maven` | `repo1.maven.org`, `repo.maven.apache.org`, `central.sonatype.com` |
| `nuget` | `api.nuget.org`, `www.nuget.org` |

You can also add **custom domains** (one per line) — e.g. `api.openai.com`, `huggingface.co`.

---

## Creating a Code Interpreter Tool

### Via the UI

1. Go to **Agents > (your agent) > Tools tab > Add Tool**
2. Pick the **Code Interpreter** template (terminal icon)
3. Fill in:
   - **Tool Name**: e.g. `run_code`
   - **Tool Category**: pick or create one (e.g. "Code Execution")
   - **Description**: e.g. "Execute Python/JS/Bash code in a sandboxed environment"
   - **Operation Type**: `Code Interpreter` (auto-selected from template)
4. Configure **Network Policy**:
   - Choose a mode: Disabled / Whitelist / Open
   - If Whitelist: toggle presets (pip, npm, etc.) and add custom domains
5. Click **Create & Add Tool**

### Via the Frappe Desk (backend)

1. Go to `Agent Tool Function > New`
2. Set `Types` = `Code Interpreter`
3. The **Network Policy** section appears:
   - `Network Mode`: `disabled`, `whitelist`, or `open`
   - `Network Presets`: JSON array, e.g. `["pip", "npm"]`
   - `Allowed Domains`: newline-separated, e.g.:
     ```
     api.openai.com
     huggingface.co
     ```
4. Save

### Via Python (bench console)

```python
import frappe

tool = frappe.get_doc({
    "doctype": "Agent Tool Function",
    "tool_name": "run_python_code",
    "tool_type": "Code Execution",       # or whatever Agent Tool Type you created
    "types": "Code Interpreter",
    "description": "Execute Python code with pip access",
    "network_mode": "whitelist",
    "network_presets": '["pip"]',
    "allowed_domains": "api.openai.com\nhuggingface.co",
})
tool.insert()
frappe.db.commit()
```

---

## Wiring a Sandbox Runtime

The `handle_code_interpreter()` function in `huf/ai/sdk_tools.py` is currently a **stub** — it logs the request and returns an error explaining the sandbox isn't wired yet.

To connect a real sandbox (e.g. [OpenSandbox](https://opensandbox.dev), [E2B](https://e2b.dev), [Daytona](https://daytona.io), or a custom Docker-based runner), edit the function:

```python
# huf/ai/sdk_tools.py — inside handle_code_interpreter()

# Replace the stub with your sandbox client:
from huf.ai.sandbox_client import SandboxClient

client = SandboxClient(
    base_url="http://localhost:8080",   # or remote URL
    # api_key="...",                    # if the runtime needs auth
)

result = client.run(
    code=code,
    language=language,
    timeout=timeout,
    network=config,   # {"network": "whitelist", "allowed_domains": [...]}
)

return {
    "success": True,
    "stdout": result.stdout,
    "stderr": result.stderr,
    "exit_code": result.exit_code,
    "files": result.output_files,   # if the sandbox returns generated files
}
```

The `config` dict has one of three shapes:

```python
{"network": "block_all"}                                    # disabled
{"network": "whitelist", "allowed_domains": ["pypi.org"]}   # whitelist
{"network": "allow_all"}                                    # open
```

Your sandbox runtime must interpret these and enforce network rules (e.g. via iptables, nftables, or container networking).

---

## Deployment Scenarios

### Scenario A — Local Bench + Local Docker

**Setup**: Frappe bench running natively on your machine. Docker used only for the sandbox runtime.

```
┌──────────────────────────────────┐
│  Your Machine                    │
│                                  │
│  ┌──────────┐   HTTP    ┌──────────────────┐
│  │  Frappe   │ ────────▶ │  Sandbox Runtime │
│  │  Bench    │ :8080     │  (Docker)        │
│  │  :8000    │           │                  │
│  └──────────┘           └──────────────────┘
│                                  │
└──────────────────────────────────┘
```

**Step 1 — Start a sandbox runtime container**

Using a hypothetical OpenSandbox image (substitute with your chosen runtime):

```bash
# Pull the sandbox runtime image
docker pull ghcr.io/example/sandbox-runtime:latest

# Run it — expose on port 8080
docker run -d \
  --name huf-sandbox \
  -p 8080:8080 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  ghcr.io/example/sandbox-runtime:latest
```

> **Note**: Mounting the Docker socket (`/var/run/docker.sock`) lets the sandbox runtime spawn sibling containers. If your runtime doesn't need this (e.g. it runs code in-process), skip the `-v` flag.

**Step 2 — Point HUF at it**

In your sandbox client code, set:

```python
client = SandboxClient(base_url="http://localhost:8080")
```

Or store the URL in `Agent Settings` / `site_config.json`:

```bash
bench --site mysite.localhost set-config sandbox_url http://localhost:8080
```

**Step 3 — Test**

```bash
# From bench console
bench --site mysite.localhost console
```

```python
from huf.ai.sandbox_policy import NetworkPolicy

policy = NetworkPolicy(mode="whitelist", presets=["pip"])
print(policy.to_sandbox_config())
# {'network': 'whitelist', 'allowed_domains': ['pypi.org', 'files.pythonhosted.org', 'pypi.python.org']}

print(policy.resolved_domains())
# ['pypi.org', 'files.pythonhosted.org', 'pypi.python.org']
```

---

### Scenario B — HUF in Docker + Host Docker Engine

**Setup**: HUF itself runs inside the `docker/docker-compose.yml` stack. The sandbox runtime also runs on the host's Docker engine.

```
┌──────────────────────────────────────────────┐
│  Host Machine (Docker Engine)                │
│                                              │
│  ┌─── docker-compose (huf) ───────────┐     │
│  │  mariadb   redis   frappe (:8000)  │     │
│  │                      │             │     │
│  │              HTTP to sandbox        │     │
│  └──────────────────────┼─────────────┘     │
│                         │                    │
│                         ▼                    │
│              ┌──────────────────┐            │
│              │  Sandbox Runtime │            │
│              │  (separate       │            │
│              │   container)     │            │
│              │  :8080           │            │
│              └──────────────────┘            │
└──────────────────────────────────────────────┘
```

**The challenge**: The `frappe` container needs to reach the sandbox container running on the host.

**Option 1 — Shared Docker network (recommended)**

```bash
# 1. Create a shared network
docker network create huf-net

# 2. Start HUF stack on this network
cd docker
# Add to docker-compose.yml:
#   networks:
#     default:
#       name: huf-net
#       external: true
docker compose up -d

# 3. Start sandbox runtime on the same network
docker run -d \
  --name huf-sandbox \
  --network huf-net \
  -p 8080:8080 \
  ghcr.io/example/sandbox-runtime:latest
```

From inside the `frappe` container, the sandbox is reachable at:

```python
client = SandboxClient(base_url="http://huf-sandbox:8080")
```

**Option 2 — host.docker.internal (macOS/Windows)**

If you can't create a shared network:

```python
# Works on Docker Desktop (macOS / Windows)
client = SandboxClient(base_url="http://host.docker.internal:8080")
```

**Option 3 — Host network gateway (Linux)**

```python
# Linux: use the docker bridge gateway IP
# Usually 172.17.0.1 — check with:  docker network inspect bridge
client = SandboxClient(base_url="http://172.17.0.1:8080")
```

Or add `extra_hosts` to the `frappe` service in `docker-compose.yml`:

```yaml
services:
  frappe:
    # ... existing config ...
    extra_hosts:
      - "host.docker.internal:host-gateway"
```

Then use `http://host.docker.internal:8080` from inside the container.

**Adding the sandbox to docker-compose.yml directly**

The simplest approach — add it as another service:

```yaml
# docker/docker-compose.yml
services:
  mariadb:
    # ... existing ...

  redis:
    # ... existing ...

  frappe:
    # ... existing ...
    depends_on:
      - mariadb
      - redis
      - sandbox    # add dependency

  sandbox:
    image: ghcr.io/example/sandbox-runtime:latest
    ports:
      - "8080:8080"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock  # if needed
    restart: unless-stopped
```

From `frappe` service, reach it at `http://sandbox:8080` (Docker DNS).

---

### Scenario C — Remote VPS (DigitalOcean / Hetzner / AWS)

**Setup**: HUF runs on your local machine or a server. The sandbox runtime runs on a separate VPS for isolation and security.

```
┌──────────────┐   HTTPS   ┌──────────────────────────┐
│  Your Server │ ────────▶ │  VPS (e.g. DigitalOcean) │
│  (HUF)       │           │                          │
│  :8000       │           │  Sandbox Runtime :443    │
└──────────────┘           │  (Docker + Caddy/nginx)  │
                           └──────────────────────────┘
```

#### Step 1 — Provision the VPS

DigitalOcean example (use any provider):

```bash
# Create a droplet (2 vCPU, 4 GB RAM minimum recommended)
doctl compute droplet create huf-sandbox \
  --region nyc1 \
  --size s-2vcpu-4gb \
  --image docker-20-04 \
  --ssh-keys <your-ssh-key-id>
```

Or via the DigitalOcean dashboard:
1. Create Droplet > Marketplace > **Docker on Ubuntu**
2. Choose plan: 2 vCPU / 4 GB ($24/mo) or higher
3. Add your SSH key
4. Create

#### Step 2 — Install the sandbox runtime on the VPS

```bash
# SSH into the VPS
ssh root@<VPS_IP>

# Pull and run the sandbox runtime
docker run -d \
  --name huf-sandbox \
  --restart unless-stopped \
  -p 127.0.0.1:8080:8080 \
  ghcr.io/example/sandbox-runtime:latest
```

> We bind to `127.0.0.1` so it's not publicly exposed — Caddy/nginx will reverse-proxy with TLS.

#### Step 3 — Set up HTTPS with Caddy (recommended)

```bash
# Install Caddy
apt update && apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list
apt update && apt install caddy

# Configure reverse proxy
cat > /etc/caddy/Caddyfile << 'EOF'
sandbox.yourdomain.com {
    reverse_proxy localhost:8080

    # Optional: restrict to your HUF server's IP
    @blocked not remote_ip <YOUR_HUF_SERVER_IP>
    respond @blocked 403
}
EOF

# Reload Caddy (auto-provisions Let's Encrypt TLS)
systemctl reload caddy
```

Point a DNS A record for `sandbox.yourdomain.com` to `<VPS_IP>`.

#### Step 4 — Secure with API key

Most sandbox runtimes support API key auth. Set a key on the VPS:

```bash
docker run -d \
  --name huf-sandbox \
  --restart unless-stopped \
  -p 127.0.0.1:8080:8080 \
  -e API_KEY=sk-sandbox-your-secret-key-here \
  ghcr.io/example/sandbox-runtime:latest
```

#### Step 5 — Configure HUF to use the remote sandbox

In your sandbox client:

```python
client = SandboxClient(
    base_url="https://sandbox.yourdomain.com",
    api_key="sk-sandbox-your-secret-key-here",
)
```

Or store in `site_config.json`:

```bash
bench --site mysite.localhost set-config sandbox_url https://sandbox.yourdomain.com
bench --site mysite.localhost set-config sandbox_api_key sk-sandbox-your-secret-key-here
```

#### Step 6 — Firewall rules (VPS)

```bash
# Allow only SSH + HTTPS, block everything else
ufw default deny incoming
ufw allow ssh
ufw allow 443/tcp
ufw enable
```

For extra security, restrict port 443 to only your HUF server's IP:

```bash
ufw allow from <HUF_SERVER_IP> to any port 443 proto tcp
```

---

## Testing the Integration

### 1. Test NetworkPolicy directly (bench console)

```bash
bench --site mysite.localhost console
```

```python
from huf.ai.sandbox_policy import NetworkPolicy

# Disabled mode
p = NetworkPolicy(mode="disabled")
print(p.to_sandbox_config())
# {'network': 'block_all'}

# Whitelist with presets
p = NetworkPolicy(mode="whitelist", presets=["pip", "npm"], domains=["api.openai.com"])
print(p.to_sandbox_config())
# {
#   'network': 'whitelist',
#   'allowed_domains': [
#     'pypi.org', 'files.pythonhosted.org', 'pypi.python.org',
#     'registry.npmjs.org', 'registry.yarnpkg.com', 'npmjs.org',
#     'api.openai.com'
#   ]
# }

# Open mode
p = NetworkPolicy(mode="open")
print(p.to_sandbox_config())
# {'network': 'allow_all'}

# From a tool document
tool = frappe.get_doc("Agent Tool Function", "run_python_code")
p = NetworkPolicy.from_tool_doc(tool)
print(p.to_dict())
```

### 2. Test from the tool handler (without a real sandbox)

The stub handler logs to the error log and returns a structured error:

```python
from huf.ai.sdk_tools import handle_code_interpreter

result = handle_code_interpreter(
    code="print('hello world')",
    language="python",
    timeout=10,
    sandbox_config={"network": "block_all"},
)
print(result)
# {
#   'success': False,
#   'error': 'Sandbox runtime is not configured yet...',
#   'sandbox_config': {'network': 'block_all'},
#   'language': 'python',
#   'timeout': 10
# }
```

### 3. Test via the Agent (end-to-end)

1. Create an Agent with a Code Interpreter tool attached
2. Open the chat UI (`/huf/chat`)
3. Ask: _"Write a Python script that prints the first 10 Fibonacci numbers"_
4. The agent will emit a `tool_call` with `code`, `language`, `timeout`
5. Until a sandbox runtime is wired, you'll see the stub error in the tool result
6. Once wired, you'll see actual stdout/stderr

### 4. Test preset expansion

```python
from huf.ai.sandbox_policy import NetworkPolicy

# Check all available presets
info = NetworkPolicy.get_preset_info()
for preset in info:
    print(f"{preset['id']:10s} → {', '.join(preset['domains'])}")
```

### 5. Verify via curl (if your sandbox runtime has an API)

```bash
# Direct sandbox test (adjust to your runtime's API)
curl -X POST http://localhost:8080/execute \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-sandbox-your-secret-key-here" \
  -d '{
    "code": "print(1 + 1)",
    "language": "python",
    "timeout": 10,
    "network": {
      "mode": "block_all"
    }
  }'
```

---

## Security Notes

1. **NetworkPolicy is deterministic** — The LLM agent has no influence over the policy. It is read from the tool document at tool-creation time, before any LLM interaction.

2. **Timeout is capped** — `handle_code_interpreter` enforces `min(timeout, 300)`. The sandbox runtime should also enforce its own timeout.

3. **Network enforcement must happen at the sandbox level** — HUF sends the policy config; the sandbox runtime is responsible for actually blocking traffic (iptables, nftables, network namespaces, etc.). HUF cannot enforce network rules from Python alone.

4. **Whitelist is domain-based** — The sandbox runtime must resolve domains to IPs and enforce at the firewall level. Be aware of DNS rebinding if your threat model requires it.

5. **`open` mode should be used carefully** — Only enable when the code source is fully trusted (e.g., your own agents running your own code, not user-supplied).

6. **Docker socket access** — If you mount `/var/run/docker.sock` into the sandbox runtime, it has root-equivalent access to the host. Only do this if the runtime needs to spawn sibling containers, and restrict it appropriately.

---

## API Reference

### `NetworkPolicy` class (`huf.ai.sandbox_policy`)

```python
class NetworkPolicy:
    def __init__(
        self,
        mode: str = "disabled",        # "disabled" | "whitelist" | "open"
        presets: list[str] | None,      # ["pip", "npm", "apt", ...]
        domains: list[str] | None,      # ["api.example.com", ...]
    )

    @classmethod
    def from_tool_doc(cls, tool_doc) -> NetworkPolicy
        # Build from an Agent Tool Function document

    @classmethod
    def get_preset_info(cls) -> list[dict]
        # Returns: [{"id": "pip", "label": "pip / PyPI", "domains": [...]}, ...]

    def resolved_domains(self) -> list[str]
        # Expands presets + extra_domains into flat deduplicated list

    def to_sandbox_config(self) -> dict
        # Returns: {"network": "block_all"} or
        #          {"network": "allow_all"} or
        #          {"network": "whitelist", "allowed_domains": [...]}

    def to_dict(self) -> dict
        # For storage/logging
```

### `handle_code_interpreter()` (`huf.ai.sdk_tools`)

```python
def handle_code_interpreter(
    code: str,                          # Source code to execute
    language: str = "python",           # python | javascript | bash | sh | ruby | php
    timeout: int = 30,                  # Max seconds (capped at 300)
    sandbox_config: dict | None = None, # From NetworkPolicy.to_sandbox_config()
    **kwargs,
) -> dict
    # Returns: {"success": bool, "stdout": str, "stderr": str, ...}
```

### Agent Tool Function DocType fields (Code Interpreter)

| Field | Type | Description |
|-------|------|-------------|
| `network_mode` | Select | `disabled` / `whitelist` / `open` (default: `disabled`) |
| `network_presets` | Small Text | JSON array of preset ids, e.g. `["pip","npm"]` |
| `allowed_domains` | Text | Newline-separated custom domains |

These fields are only visible when `types == "Code Interpreter"`.

### Tool parameters (sent to LLM)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `code` | string | Yes | Source code to execute |
| `language` | string (enum) | No | `python`, `javascript`, `bash`, `sh`, `ruby`, `php` (default: `python`) |
| `timeout` | integer | No | Max execution time in seconds (default: 30, max: 300) |
