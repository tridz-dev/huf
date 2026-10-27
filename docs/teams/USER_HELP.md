# Using Huf in Microsoft Teams

Written from the implemented behaviour. Your administrator must have installed the Huf app in
Teams for you. If the bot never answers, ask your administrator (see ADMIN_SETUP.md).

## 1. Connect your Huf account

The bot does not know which Huf account is yours until you connect it once.

1. Open a **personal chat** with the Huf app in Teams and send `connect`.
2. The bot replies with a link. Open it in a browser while logged in to Huf with **your own**
   account. The link works once and expires after 10 minutes. It is not sent again if you ask
   twice within 2 minutes; the same link is repeated.
3. The page shows the Teams person and organisation and the Huf account you are logged in as.
   Tick the acknowledgement and confirm. Then go back to Teams.
4. Send `status` to check.

If you are not connected and ask a normal question, the bot answers with the same connect
instructions instead of running anything. From then on your requests run as **your** Huf user,
with your own Huf permissions. The bot never falls back to a shared account.

Things that stop a connection:

- Guest and external Microsoft accounts are not supported.
- The link must be opened by a logged-in, enabled Huf user who is not Guest or Administrator.
- One Teams account can be linked to only one Huf user, and one Huf user to only one Teams account
  per organisation. The page tells you if it is already linked elsewhere.
- Expired or already-used links show an error; send `connect` again.
- If your Huf account is disabled, the bot says so and asks you to contact an administrator.

An administrator can also link you from the Teams people panel; you then do not need `connect`.

## 2. Commands

Send these as the whole message (case does not matter; a leading `/` is accepted). They are answered
instantly and do not use an agent.

| Command | Where | What it does |
|---|---|---|
| `help` | personal chat, group chat, channel | Explains what you can do. If you are not connected it adds the first-contact text and how to connect |
| `connect` | **personal chat only** | Sends your one-time link. If already connected, says which Huf account |
| `status` | **personal chat only** | Shows the connected Huf account and your last 5 requests (id, status, time) |
| `disconnect` | any chat | Disconnects your Huf account from Teams |

In a channel or group chat, `connect` and `status` do not do their job; the bot tells you to open a
personal chat and send the word there. Links are never posted in channels.

You can also type the commands from the app's command list in Teams (help, connect, status,
disconnect). Other text-based preferences (quiet hours, opt-out) do not exist yet.

## 3. What the bot can do

- Answer questions and run the agents and workflows your administrator routed to this bot,
  using the tools and records **your Huf account** may access.
- Work in a **personal chat** (every message), and in **channels or group chats when you @mention
  the bot** (the mention text is removed before the agent reads it). Messages that do not mention
  the bot are not read.
- Keep a separate conversation context for each person in a channel or group chat, so one person's
  context is not shown to another.
- Send you approvals and notifications as private messages (sections 5 and 6).

It does not read your files, calendar or email, does not open meetings, and does not search Teams
history (see UNSUPPORTED.md).

## 4. Privacy in channels

Depending on a tenant setting, an answer to a channel or group-chat question may be delivered to you
privately instead of in the room.

- In the room you see only a short note: "I sent you the answer in a private chat."
- The answer goes to your personal chat with the bot. The default setting does this whenever the
  agent used any tool other than a small safe list (calculator, current time, knowledge search),
  i.e. whenever Huf records may have been touched. Administrators can choose "Always private" or "Channel".
- If you have never opened a private chat with the bot and it cannot start one, the bot posts "Open a
  private chat with me and send "hi" so I can reply privately." and does **not** put the answer in the room.
  Send "hi" to the bot in a personal chat and ask again.
- Personal chats are never redirected.

## 5. Approvals by card

When a Huf execution approval (code or command execution) is created and you are an approver
(named user or member of the approver role, and not the requester), the bot sends an Adaptive Card to
your personal chat with **Approve** and **Reject**.

- The card shows only kind, capability, reference and expiry.
- Your click is checked against **your** Teams identity and your Huf permissions, not who the card was
  sent to. If you are not allowed, you see a refusal and nothing changes.
- The first valid decision wins. A second click shows "already decided". After expiry you see
  "This approval has expired."
- If you have no connected identity or no personal chat, no card is sent; decide in the Huf web app.
- After a decision the card is replaced with "Approved/Rejected by <name>".
- Some Teams clients may not render Adaptive Cards; the message also carries a plain-text fallback
  telling you to open Huf. Only execution approvals are supported; flow approvals are not.

## 6. Notifications

Huf can send you private notifications (text or card) when an administrator, a Huf app or your own
code calls the notification API for your Huf user. They arrive in your personal chat with the bot.
You must have installed the app or messaged it at least once. There are no per-user notification
settings yet.

## 7. Disconnecting

Send `disconnect`. Your link is revoked immediately. The bot confirms: "Your Huf account is
disconnected from Teams. Personalized requests and notifications are paused." If you were not
connected it says so. To connect again later send `connect`. An administrator can also revoke you
from the Teams people panel. Disconnecting does not delete your Huf account or past runs.
