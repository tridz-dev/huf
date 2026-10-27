# Real Microsoft 365 tenant validation checklist (slice 1)

Why: the unit and bench tests use mocked Microsoft services. They cannot prove Teams compatibility
(SPEC section 23). The owner runs this on a real tenant. Nothing below has been run against a real
tenant yet; the expected results are derived from the code and must be confirmed.

Mark portal navigation steps **verify against current Microsoft documentation** (D1, D3, D10, D11).

## 0. Test fixtures

- A Microsoft 365 test tenant (the "home" tenant) with at least: admin A, ordinary users U1 and U2,
  and a guest user G (external or B2B guest). Optionally a second tenant T2 with user X.
- A Huf site on public HTTPS, Gateway with `direct_policy` = Open for the pilot (ADMIN_SETUP.md 3.3),
  default agent that answers simple text, and one agent that uses a tool that touches records.
- Huf users H1 (for U1) and H2 (for U2); H2 is an approver role member for execution approvals.
- A team with a standard channel and a group chat containing U1 and U2.

Evidence to capture for every test: screenshot or screen recording from Teams, the Huf Gateway Event
row (status, error_message, redacted raw_payload), the Teams diagnostics support bundle (redacted),
time of test, bot/app version. Do not capture the client secret or the Bearer token.

## 1. Setup (positive)

| # | Action | Expected observation |
|---|---|---|
| S1 | Complete ADMIN_SETUP.md sections 2 and 3 | Wizard "Test connection": `credentials_present` pass, `token_acquisition` pass |
| S2 | Open the diagnostics panel | `messaging_endpoint` shows the https URL; no check shows a secret |
| S3 | Azure Bot messaging endpoint set, Teams channel enabled | Azure accepts the URL |
| S4 | Download package, upload as admin A, install for U1 | App appears; bot's command list shows help, connect, status, disconnect |
| S5 | U1 sends `help` in personal chat, then "hello" | `help`: reply ending "Send connect to link your account." and no Gateway Event row. "hello": a Gateway Event row appears (Queued, or Rejected if admission blocks it); `last_inbound` shows it; `conversation_references` shows 1 personal (from the install event or the ordinary message) |
| S6 | Re-download package with the same version, try to re-upload | Record Teams' behaviour (not specified by Huf) |

## 2. Identity (SPEC tests 4, 15)

| # | Action | Expected |
|---|---|---|
| I1 | U1 sends `connect`; open link logged in as H1; confirm | Page shows U1 and tenant; success; `status` shows H1 |
| I2 | Re-open the same link | Error "invalid or has expired" (single use) |
| I3 | Wait 10+ minutes on a fresh link, then confirm | Same error |
| I4 | Generate a link for U1 (do not confirm). Log in to Huf as H2 and confirm it | By design the token names the Teams person (U1) and the confirming Huf user becomes the linked user. Expected: H2 is linked to U1's Teams identity (U1 then runs as H2). Record this; it is residual risk R1 in SECURITY_AND_DATA.md. A Teams person already linked is not replaced |
| I5 | U1 asks a question before linking | Connect instructions, no agent run |
| I6 | G (guest) messages the bot | "Guest and external Microsoft accounts are not supported" (if Teams provides the guest marker; record the real payload field) |
| I7 | `connect` sent in a channel and group chat | "Open a personal chat with me and send connect.", no link posted |
| I8 | U1 `disconnect`; then ask a question | Confirmation text; next question gets connect instructions; link row `Revoked` |
| I9 | Admin revokes via Teams people; disable H1 in Huf | Next message: "Your linked Huf account is disabled..." for the disabled case; no agent run |

## 3. Transport and tenant isolation (SPEC tests 2, 3, 13)

| # | Action | Expected |
|---|---|---|
| T1 | POST to the endpoint with no `Authorization` header (curl) | 401 `Provider verification failed`; no Gateway Event |
| T2 | POST with a random `Bearer abc` | 401 |
| T3 | POST with a valid-format token from another app (wrong audience) if obtainable | 401 |
| T4 | Genuine activity but `serviceUrl` edited in body (replay) | 401 (`service_url_mismatch`) |
| T5 | Remove U1's tenant from allowed list and set a different GUID in `allowed_tenants`; U1 sends a message | Event Rejected `tenant_not_allowed`; no reply; restore the list |
| T6 | (Optional) T2/X tries to install or message the bot | Not able to use it (single-tenant); record how Teams/Entra behave |
| T7 | Rotate the client secret in Entra, update Huf, restart workers | `token_acquisition` pass again; queued messages deliver |
| T8 | Use a wrong secret | `token_acquisition` fail with "Microsoft rejected the app password" |

## 4. Conversations and replies (SPEC tests 5, 7, 9)

| # | Action | Expected |
|---|---|---|
| C1 | U1 asks a plain question in personal chat | Answer arrives; outbox row `Sent` with provider id |
| C2 | In the channel, U1 @mentions the bot with a plain question | Answer (policy `Channel`, or default with no tool use) appears in the same thread |
| C3 | In the channel, U1 asks something that makes the agent use a record tool (default policy) | Room shows "I sent you the answer in a private chat."; the answer is in U1's personal chat; **no** record title or error text in the channel |
| C4 | Repeat C3 with policy `Always private` and a trivial question | Private as well |
| C5 | U2 mentions the bot in the same channel thread afterwards | U2's context contains nothing from U1's conversation |
| C6 | Uninstall the app from U1's personal scope, repeat C3 | Channel gets a neutral "Open a private chat..." note, answer is not posted to the room |
| C7 | Group chat mention | Works as channel for mentions; no reply to non-mention messages |
| C8 | Re-send the same activity (retry from Azure Web Chat/replay) | One run only (idempotency by activity id) |
| C9 | Stop workers, send a message, start workers | Message processed once; outbox delivers once |
| C10 | Block outbound to the connector (firewall) briefly | Outbox row `Pending` with backoff, then `Sent` after recovery; failed delivery never reruns the agent |

## 5. Approvals and notifications (SPEC tests 8, 10)

| # | Action | Expected |
|---|---|---|
| A1 | Create an Agent Execution Approval naming H2 as approver | H2 receives a card in personal chat on desktop, web, mobile; record rendering on each |
| A2 | H2 clicks Approve | Card replaced by "Approved by H2"; approval status Approved with comment "Decided via Microsoft Teams" |
| A3 | H2 clicks again / another approver clicks | "already decided"/"no longer pending"; no change |
| A4 | Approval expires, click | "This approval has expired." |
| A5 | Unlinked user clicks a forwarded card (if forwardable) | "Your Teams account is not connected to Huf..." |
| A6 | `send_teams_notification` for H1 (text and card) | Message in personal chat; repeat with same `dedupe_key` returns `deduped: true` |
| A7 | Notification for a user who never installed or messaged | `success: false` with plain-language error; or Teams creates the chat if the app is installed. Record |
| A8 | Record whether the keyboard/text fallback for cards works | Plain-text fallback line is present |

## 6. Negative/edge checks to record

Mention rendering (`<at>` removed from agent input), very long reply (Teams message size), Markdown
rendering, behaviour with `direct_policy` at its default (expect Rejected "Sender is not approved"),
bot behaviour in a private or shared channel (unsupported: just record).

## 7. Sign-off

Pass criteria: S1-S5, I1-I3, I5, I7-I8, T1-T5, C1-C3, C5, C8, A1-A3 pass; I4, I6, C6, C10, T6, A7 results
recorded and reviewed against SECURITY_AND_DATA.md. File issues for every deviation.

## 8. Rollback and teardown

1. In Huf, disable the Gateway (Microsoft then gets HTTP 403). Optionally set `is_enabled` back later.
2. Revoke all links (Teams people panel) so no identities remain `Linked`.
3. In Teams admin center remove the app from users/org (verify, D10). Remove the app from teams.
4. In Azure, remove the Teams channel or delete the Azure Bot resource; delete the client secret and,
   if not reused, the Entra app registration.
5. Delete the Integration Settings credentials in Huf (secret is stored encrypted).
6. Optional data removal (nothing purges automatically; SECURITY_AND_DATA.md section 3): delete Teams
   Conversation Reference, Teams Outbound Message, Teams Action Session rows for the gateway, the Gateway
   Identity Link rows with provider `Microsoft Teams`, and Gateway Events for the gateway.
7. Remove the Huf test agents/approvals created for the test.
Rollback of the code: revert the merge of `feat/teams-p0`; Teams doctypes remain in the database until dropped.
