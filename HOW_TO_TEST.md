# How to Test Community Subscription Adapters

> Branch: `feat/community-subscription-adapters`  
> Container: `fdocker_devcontainer-frappe-1`  
> Bench path (inside container): `/workspace/development/16`  
> Site: `huf.localhost`  
> Host URL: `http://huf.localhost:8100`

## What this branch adds

- A new **AI Provider Connection** DocType that stores per-user OAuth/device-code tokens.
- A subscription-adapter registry under `huf/ai/providers/adapters/`.
- Community adapters that reuse public client credentials from popular AI CLI plugins:
  - **OpenAI Community** (`openai_community_subscription`) — OAuth PKCE, manual paste flow.
  - **Kimi For Coding** (`kimi_community_subscription`) — OAuth device flow.
  - **Mock** (`mock_subscription`) — for CI / offline regression tests.
- An OAuth callback page at `/huf/sub_oauth`.
- Routing changes in `huf/ai/run.py` and `huf/ai/agent_integration.py` so agents can run through a subscription connection even when the shared AI Provider has no API key.

> ⚠️ These adapters use **community-reversed OAuth client IDs**. They are not official integrations. Enable them only for experimentation; using them with real accounts may violate the provider’s Terms of Service.

---

## 1. Environment setup

Run all bench commands through the Frappe container:

```bash
docker exec fdocker_devcontainer-frappe-1 bash -c "cd /workspace/development/16 && bench --site huf.localhost <COMMAND>"
```

### 1.1 Build the frontend SPA

The HUF UI is a Vite SPA. After pulling the branch, build it with **yarn** inside the container:

```bash
docker exec fdocker_devcontainer-frappe-1 bash -c "cd /workspace/development/16/apps/huf/frontend && yarn build"
```

Do not use `npm run build` for HUF/Frappe apps in this bench.

### 1.2 Migrate the site

```bash
docker exec fdocker_devcontainer-frappe-1 bash -c "cd /workspace/development/16 && bench --site huf.localhost migrate"
```

### 1.2 Enable the adapters

```bash
docker exec fdocker_devcontainer-frappe-1 bash -c "cd /workspace/development/16 && \
  bench --site huf.localhost set-config enable_openai_community_subscription_adapter 1 && \
  bench --site huf.localhost set-config enable_kimi_community_subscription_adapter 1 && \
  bench --site huf.localhost set-config enable_mock_subscription_adapter 1"
```

### 1.3 Verify the callback page

From your Mac:

```bash
curl -s -o /dev/null -w '%{http_code}' http://huf.localhost:8100/huf/sub_oauth
# Expected: 200
```

---

## 2. Use the HUF UI (recommended)

### 2.1 Open the Subscription Connections page

Go to **AI Providers** (`http://huf.localhost:8100/huf/providers`) and click **Connections** in the top-right.

Or visit directly:

```
http://huf.localhost:8100/huf/provider-connections
```

### 2.2 Create a connection

1. Click **Add Connection**.
2. Fill in:
   - **Connection Name**: anything unique
   - **AI Provider**: pick the provider you created (brand must be `openai_community` or `kimi_community`)
   - **Adapter Type**: `openai_community_subscription` or `kimi_community_subscription`
   - **Auth Method**: auto-populated from the adapter
   - **Eligible Models**: `["gpt-4o"]` or `["kimi-for-coding"]`
3. Click **Create Connection**.

### 2.3 Authorize

For **OpenAI Community**:

1. Click **Authorize** on the connection row.
2. Open the printed **Authorization URL** in a new tab.
3. After authorizing, copy the final browser URL (`https://...?code=...&state=...`).
4. Paste it into the **Pasted Callback URL** field.
5. Click **Complete Authorization**.

For **Kimi For Coding**:

1. Click **Authorize** on the connection row.
2. Open the **verification page** link in a new tab.
3. Enter the displayed **User Code** on the Kimi site.
4. Click **Complete Authorization** in HUF.

Status changes to `Active` when successful.

### 2.4 Run an agent

Create or run an Agent with:

| Field | Value |
|-------|-------|
| AI Provider | `OpenAI Community` or `Kimi For Coding` |
| Model | `gpt-4o` or `kimi-for-coding` |

The runtime auto-discovers the active connection for the current user.

## 3. Run the test suite

```bash
docker exec fdocker_devcontainer-frappe-1 bash -c "cd /workspace/development/16 && \
  bench --site huf.localhost run-tests --module huf.ai.tests.test_subscription_adapter_mock && \
  bench --site huf.localhost run-tests --module huf.ai.tests.test_subscription_adapter_openai_community && \
  bench --site huf.localhost run-tests --module huf.ai.tests.test_subscription_adapter_kimi_community"
```

Expected results:

| Module | Tests |
|--------|-------|
| `test_subscription_adapter_mock` | 7 passed |
| `test_subscription_adapter_openai_community` | 8 passed |
| `test_subscription_adapter_kimi_community` | 9 passed |

---

## 4. Test the OpenAI Community adapter (live OAuth)

### 3.1 Create the AI Provider

Open `http://huf.localhost:8100/app/ai-provider/new` and enter:

| Field | Value |
|-------|-------|
| Provider Name | `OpenAI Community` |
| Provider Brand | `openai_community` |
| API Key | *(leave blank)* |

Save.

### 3.2 Create the AI Provider Connection

Open `http://huf.localhost:8100/app/ai-provider-connection/new` and enter:

| Field | Value |
|-------|-------|
| Connection Name | `OpenAI Community Test` |
| User | your user |
| AI Provider | `OpenAI Community` |
| Adapter Type | `openai_community_subscription` |
| Auth Method | `OAuth PKCE (Manual Paste)` |
| Is Active | ✅ |
| Eligible Models | `["gpt-4o"]` |

Save.

### 3.3 Start authorization

Run in bench:

```bash
docker exec fdocker_devcontainer-frappe-1 bash -c "cd /workspace/development/16 && bench --site huf.localhost execute \"from huf.ai.providers.adapters import get_adapter; c=frappe.get_doc('AI Provider Connection','OpenAI Community Test'); a=get_adapter(c.adapter_type); r=a.start_authorization(c,'OAuth PKCE (Manual Paste)'); c.save(ignore_permissions=True); print(r['auth_url'])\""
```

Open the printed URL in your browser, authorize, then copy the final browser URL (the one containing `?code=...&state=...`).

### 3.4 Complete authorization

```bash
docker exec fdocker_devcontainer-frappe-1 bash -c "cd /workspace/development/16 && bench --site huf.localhost execute \"from huf.ai.providers.adapters import get_adapter; c=frappe.get_doc('AI Provider Connection','OpenAI Community Test'); a=get_adapter(c.adapter_type); r=a.complete_authorization(c,{'pasted_url':'PASTE_URL_HERE'}); c.save(ignore_permissions=True); print(r)\""
```

`auth_status` should change to `Active`.

### 3.5 Run an agent

Create or run an Agent with:

| Field | Value |
|-------|-------|
| AI Provider | `OpenAI Community` |
| Model | `gpt-4o` |

Or call programmatically:

```python
from huf.ai.agent_integration import run_agent_sync
run_agent_sync(
    agent="Your Agent",
    prompt="Hello",
    provider="OpenAI Community",
    model="gpt-4o",
    subscription_connection_name="OpenAI Community Test",
)
```

---

## 5. Test the Kimi For Coding adapter (device flow)

### 4.1 Create the AI Provider

Open `http://huf.localhost:8100/app/ai-provider/new`:

| Field | Value |
|-------|-------|
| Provider Name | `Kimi For Coding` |
| Provider Brand | `kimi_community` |
| API Key | *(leave blank)* |

Save.

### 4.2 Create the AI Provider Connection

Open `http://huf.localhost:8100/app/ai-provider-connection/new`:

| Field | Value |
|-------|-------|
| Connection Name | `Kimi Test` |
| User | your user |
| AI Provider | `Kimi For Coding` |
| Adapter Type | `kimi_community_subscription` |
| Auth Method | `Device Code` |
| Is Active | ✅ |
| Eligible Models | `["kimi-for-coding"]` |

Save.

### 4.3 Start device authorization

```bash
docker exec fdocker_devcontainer-frappe-1 bash -c "cd /workspace/development/16 && bench --site huf.localhost execute \"from huf.ai.providers.adapters import get_adapter; c=frappe.get_doc('AI Provider Connection','Kimi Test'); a=get_adapter(c.adapter_type); r=a.start_authorization(c,'Device Code'); c.save(ignore_permissions=True); print(r)\""
```

The output contains `user_code` and `verification_uri`. Open the URI in your browser, enter the user code, and approve.

### 4.4 Complete authorization

While the browser flow is active, run:

```bash
docker exec fdocker_devcontainer-frappe-1 bash -c "cd /workspace/development/16 && bench --site huf.localhost execute \"from huf.ai.providers.adapters import get_adapter; c=frappe.get_doc('AI Provider Connection','Kimi Test'); a=get_adapter(c.adapter_type); r=a.complete_authorization(c,{}); c.save(ignore_permissions=True); print(r)\""
```

The adapter polls the token endpoint until approval or expiry.

### 4.5 Run an agent

```python
from huf.ai.agent_integration import run_agent_sync
run_agent_sync(
    agent="Your Agent",
    prompt="Hello",
    provider="Kimi For Coding",
    model="kimi-for-coding",
    subscription_connection_name="Kimi Test",
)
```

---

## 6. Useful URLs

| URL | Purpose |
|-----|---------|
| `http://huf.localhost:8100/huf` | HUF frontend SPA |
| `http://huf.localhost:8100/huf/sub_oauth` | OAuth callback page |
| `http://huf.localhost:8100/app/ai-provider` | AI Provider list |
| `http://huf.localhost:8100/app/ai-provider-connection` | AI Provider Connection list |

---

## 7. Optional site config overrides

### OpenAI Community

```bash
bench --site huf.localhost set-config openai_community_oauth_client_id '<client_id>'
bench --site huf.localhost set-config openai_community_auth_url '<auth_url>'
bench --site huf.localhost set-config openai_community_token_url '<token_url>'
bench --site huf.localhost set-config openai_community_api_base_url '<api_base>'
```

### Kimi Community

```bash
bench --site huf.localhost set-config kimi_community_oauth_client_id '<client_id>'
bench --site huf.localhost set-config kimi_community_oauth_device_auth_url '<device_auth_url>'
bench --site huf.localhost set-config kimi_community_oauth_token_url '<token_url>'
bench --site huf.localhost set-config kimi_community_api_base_url '<api_base>'
bench --site huf.localhost set-config kimi_community_device_id '<stable_hex_uuid>'
```

Defaults are hard-coded to the values used by the referenced community plugins.

---

## 8. Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `PermissionError: ... adapter is disabled` | Feature flag is off | Set the relevant `enable_*_subscription_adapter` config to `1` |
| `API Key is required for cloud providers` | Provider brand not in `SUBSCRIPTION_BRANDS` | Use `openai_community` or `kimi_community` brand |
| `/huf/sub_oauth` returns 404 | DocType/page not migrated | Run `bench --site huf.localhost migrate` |
| `subscription connection is expired` | Token refresh failed | Re-run the authorization flow |
| Tests fail with `KeyError: 'url'` | Tests out of sync with adapter | Pull the latest branch; positional/keyword URL assertions were aligned |

---

## 9. Files changed

```
huf/ai/agent_integration.py
huf/ai/run.py
huf/ai/providers/adapters/__init__.py
huf/ai/providers/adapters/base.py
huf/ai/providers/adapters/mock.py
huf/ai/providers/adapters/openai.py
huf/ai/providers/adapters/openai_community.py
huf/ai/providers/adapters/kimi_community.py
huf/ai/tests/test_subscription_adapter_mock.py
huf/ai/tests/test_subscription_adapter_openai_community.py
huf/ai/tests/test_subscription_adapter_kimi_community.py
huf/huf/doctype/ai_provider/ai_provider.json
huf/huf/doctype/ai_provider/ai_provider.py
huf/huf/doctype/ai_provider_connection/ai_provider_connection.py
huf/www/sub_oauth.py
huf/www/sub_oauth.html
frontend/src/App.tsx
frontend/src/components/AiProvidersHeaderActions.tsx
frontend/src/data/doctypes.ts
frontend/src/pages/AiProviderConnectionsPage.tsx
frontend/src/pages/AiProviderConnectionsPageWrapper.tsx
frontend/src/services/providerConnectionApi.ts
HOW_TO_TEST.md
```
