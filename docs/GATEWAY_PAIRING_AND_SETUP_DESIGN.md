# Seamless Gateway Setup & Interactive Pairing Architecture for Huf

> **Status**: Proposed Design & Implementation (PR Pending Verification)  
> **Target System**: Huf AI Agent Platform (`huf`)  
> **Key Goal**: Provide a 100% UI-native and Chat-guided experience for connecting, configuring, and pairing channel gateways (Telegram, WhatsApp, Discord, Slack, Email, SMS, Google Chat, Microsoft Teams) without requiring users to visit Frappe Desk.

---

## 1. Executive Summary & Philosophy

Historically, configuring enterprise webhooks, chat bot credentials, and access control required navigating complex Desk forms, manually crafting JSON configurations, and configuring webhook URLs across external developer portals.

Taking inspiration from **OpenClaw**'s seamless Telegram pairing and quick-setup mechanics, Huf introduces a **Chat-Guided Gateway Pairing Assistant** built directly into **Hub Chat**. 

### Core Design Principles:
1. **Zero Desk Redirection**: All gateway creation, token submission, pairing approvals, and health diagnostics happen directly inside Hub Chat or embedded Huf UI components.
2. **Conversational Guided Onboarding**: Huf AI Agents guide non-technical users step-by-step through obtaining API keys (e.g. step-by-step `@BotFather` interactions for Telegram, Twilio token setup for SMS, Meta Cloud API setup for WhatsApp).
3. **Instant Automated Probe & Webhook Setup**: Submitting credentials immediately triggers an live API probe (`getMe` / API test) and automatically registers Huf's webhook URL with the provider's API (e.g. Telegram `setWebhook`).
4. **Human-Readable 8-Character Pairing Codes (`PAIR-XXXX`)**: When unapproved users DM a bot under `Pairing` policy, an 8-character pairing code is generated. Admins can approve access directly in Hub Chat using `/pair approve PAIR-XXXX` or 1-click UI actions.
5. **Automated Welcome Feedback Loop**: Once paired, Huf automatically sends an outbound welcome message back to the user on the external channel (Telegram/WhatsApp/Discord/etc.).

---

## 2. Research & Comparison: OpenClaw vs. Huf Gateway Architecture

| Capability | OpenClaw Pattern | Huf Guided Architecture | Advantage / Outcome in Huf |
| :--- | :--- | :--- | :--- |
| **Transport Model** | Long-polling by default; optional webhooks | Serverless REST & Webhook Adapters | Zero persistent daemon processes required; fully stateless |
| **Pairing Policy** | DM Pairing required by default | Direct Policy = `Pairing` with `PAIR-XXXX` codes | Complete access control without open spam or complex allow-lists |
| **Onboarding UX** | CLI / Config file driven | Interactive Hub Chat AI Tool & Guided UI | "Piece of cake" onboarding for normal users |
| **Webhook Registration** | Manual setup or config | Automated API Webhook Push (`setWebhook`) | Webhook URLs generated & registered automatically |
| **Approval Flow** | `claw pair approve <code>` in terminal | In-chat `/pair approve PAIR-XXXX` or 1-click UI | Real-time approval with zero CLI requirement |
| **Multi-Channel** | Focused heavily on Telegram | Unified across 8+ channels (Telegram, WhatsApp, Discord, Slack, etc.) | Single unified pairing contract for all integrations |

---

## 3. High-Level System Architecture

```
                                  ┌─────────────────────────────────────────┐
                                  │               HUB CHAT                  │
                                  │   (User + Huf AI Onboarding Agent)     │
                                  └────────────────────┬────────────────────┘
                                                       │
                                 Calls Setup / Pairing Tool Functions
                                                       │
                                                       ▼
 ┌───────────────────────────────────────────────────────────────────────────────────────────┐
 │                                 HUF GATEWAY PAIRING ENGINE                                │
 │  (/huf/ai/tools/gateway_pairing_tools.py)                                                │
 │                                                                                           │
 │  ┌───────────────────────┐   ┌────────────────────────┐   ┌───────────────────────────┐  │
 │  │    setup_gateway()    │   │ list_pairing_requests()│   │  approve_pairing_code()   │  │
 │  └───────────┬───────────┘   └───────────┬────────────┘   └─────────────┬─────────────┘  │
 └──────────────┼───────────────────────────┼──────────────────────────────┼────────────────┘
                │                           │                              │
                ▼                           ▼                              ▼
 ┌───────────────────────────┐  ┌────────────────────────┐  ┌───────────────────────────┐
 │   Integration Settings    │  │  Gateway Access Entry  │  │   Gateway Adapter Reply   │
 │   & Gateway DocTypes      │  │  (state="Pending",     │  │   (Sends welcome message  │
 │   (Credentials Encrypted) │  │   code="PAIR-7A9K")    │  │    back to external DM)   │
 └───────────────────────────┘  └────────────────────────┘  └───────────────────────────┘
```

---

## 4. Technical Specifications & Tool Contracts

### 4.1. `setup_gateway` Tool
Configures or updates a channel Gateway and its connected credentials seamlessly.

```python
def setup_gateway(
    provider: str,
    gateway_name: str,
    credentials: dict[str, str],
    *,
    default_target_type: str = "Agent",
    default_agent: str | None = None,
    default_flow: str | None = None,
    direct_policy: str = "Pairing",
    room_policy: str = "Allow list",
    room_sender_policy: str = "Allow list",
    mention_required: bool = True,
    execution_user: str | None = None,
) -> dict[str, Any]
```

#### Behavior:
1. Instantiates the provider adapter (`Telegram`, `WhatsApp`, `Discord`, `Slack`, `Email`, `SMS`, `Google Chat`, `Microsoft Teams`).
2. Runs validation on supplied credentials.
3. Automatically creates or updates `Integration Settings` and `Gateway` documents in Frappe.
4. Generates standard webhook URL: `https://<domain>/api/method/huf.ai.gateway_webhook.handle_gateway_webhook?gateway_name=<name>`.
5. For supported providers (e.g. Telegram), calls `setWebhook` API to complete registration automatically.

---

### 4.2. `approve_pairing_code` Tool
Approves a pending pairing request using its 8-character code (e.g., `PAIR-7A9K`) or record ID.

```python
def approve_pairing_code(
    pairing_code_or_id: str,
    notes: str | None = None
) -> dict[str, Any]
```

#### Behavior:
1. Finds `Gateway Access Entry` with matching `pairing_code` and `state="Pending"`.
2. Marks record as `Approved` with timestamp and approver ID.
3. Instantiates gateway adapter and sends outbound welcome notification to external sender.

---

### 4.3. `list_pairing_requests` Tool
Lists active pending pairing requests across all gateways or filtered by a specific gateway.

```python
def list_pairing_requests(gateway_name: str | None = None) -> list[dict[str, Any]]
```

---

### 4.4. `test_gateway_health` Tool
Runs diagnostic checks on gateway credentials, last active timestamps, and error logs.

```python
def test_gateway_health(gateway_name: str) -> dict[str, Any]
```

---

## 5. End-to-End User Walkthroughs

### Walkthrough 1: Connecting Telegram Bot in Hub Chat

1. **User Request**: `"I want to add a Telegram bot to Huf."`
2. **Agent Response**:
   > "I'll guide you through setting up your Telegram bot!
   > 
   > **Step 1**: Open [@BotFather](https://t.me/BotFather) on Telegram.  
   > **Step 2**: Send `/newbot`, give your bot a name and username.  
   > **Step 3**: Copy the HTTP API Token provided by BotFather and paste it here!"
3. **User Action**: Sends token `7182938475:AAFx...`.
4. **Agent Action**: Calls `setup_gateway(provider="Telegram", gateway_name="Telegram Main Bot", credentials={"token": "7182938475:AAFx..."})`.
5. **Result**:
   - Token verified via Telegram `getMe`.
   - Webhook URL automatically configured via `setWebhook`.
   - Gateway active and ready!

---

### Walkthrough 2: Approving an Inbound Telegram DM Pairing Request

1. External user `@john_doe` sends a DM to the newly configured Telegram bot.
2. The Telegram bot responds to `@john_doe`:
   > 🔒 Access approval required.  
   > Your pairing code is: **`PAIR-9B2F`**  
   > Please share this code with the bot administrator to get approved.
3. Huf Admin receives notification in Hub Chat.
4. Huf Admin types in Hub Chat: `/pair approve PAIR-9B2F`.
5. Agent calls `approve_pairing_code("PAIR-9B2F")`.
6. `@john_doe` on Telegram receives:
   > 🎉 Your access pairing request has been approved! You can now interact directly with this assistant.

---

## 6. Implementation Summary & Verification Checklist

- [x] Added `pairing_code` field to `Gateway Access Entry` DocType.
- [x] Implemented `_create_pairing_request` in `huf/ai/gateway_service.py` with automatic code generation (`PAIR-XXXX`) and outbound DM notification delivery.
- [x] Built `huf/ai/tools/gateway_pairing_tools.py` containing `setup_gateway`, `list_pairing_requests`, `approve_pairing_code`, and `test_gateway_health`.
- [x] Provided comprehensive documentation artifact for review.
