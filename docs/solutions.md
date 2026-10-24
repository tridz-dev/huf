# Solutions

A Solution is one job that Huf does on a WhatsApp number, for example "Order desk", "Support" or "Catering bookings". A Solution has its own agent or flow, its own entry points, its own templates and its own limits. Solutions let one number do several jobs without the jobs getting in each other's way.

Contents: [Words used](#words-used) - [Numbers and Solutions](#numbers-and-solutions) - [Purposes](#purposes) - [How an incoming message finds its Solution](#how-an-incoming-message-finds-its-solution) - [Entry points](#entry-points) - [Conversation pin](#conversation-pin) - [Paused and test mode](#paused-and-test-mode) - [Templates](#templates) - [Limits and the number's ceiling](#limits-and-the-numbers-ceiling) - [Message log](#message-log) - [Handing a chat to another Solution](#handing-a-chat-to-another-solution) - [Set up two jobs on one number](#set-up-two-jobs-on-one-number) - [Known limits](#known-limits)

## Words used

| Word | Meaning |
|------|---------|
| Number | One connected WhatsApp number (a Gateway in Huf). |
| Solution | A named job on one or more numbers. It answers with one agent or one flow. |
| Purpose | A label chosen when you create a Solution (see [Purposes](#purposes)). It only drives suggestions. |
| Runs on | The number or numbers a Solution answers on. |
| Entry point | A rule that sends incoming messages to a Solution: a keyword, an ad tag, a catch-all or the triage menu. |
| Pin | The memory that keeps a chat with the Solution that last answered it. |
| Ceiling | The daily send limit of a number that Solutions limits cannot exceed. |

## Numbers and Solutions

- One number can host several Solutions. This is the point of the feature: the same number can take orders and answer support questions.
- One Solution can run on several numbers. It has one set of entry points per number.
- Solutions never replace the number's own settings. The number keeps its connection, token health, allow list, opt-out handling and send limits. A Solution can only make those limits tighter (see [Limits](#limits-and-the-numbers-ceiling)).
- A number with no Solution behaves as it always did: the number's default agent or flow answers, and any older routing rules still work.

## Purposes

The purpose is chosen when you create a Solution. It sets the suggested entry points, suggested templates and policy notes in the creation wizard. It never creates an agent for you, and you can change it later.

| Purpose | What the wizard suggests |
|---------|--------------------------|
| Answer questions (`answer`) | A catch-all entry point. |
| Take orders (`orders`) | Keywords such as order, menu, cake and an ad tag. |
| Support & handoff (`support`) | Keywords such as help, refund, wrong, complaint. |
| Bookings (`bookings`) | Keywords such as book, event, quote, catering and an ad tag. |
| Send updates (`updates`) | No entry points: outbound only, using templates. |
| Team & internal (`team`) | An allow-list entry point: only allow-listed staff numbers. |
| Custom (`custom`) | Nothing suggested. Also used for "start blank". |

For a `team` Solution, every entry point is saved with the "Allow list" recipient scope.

The policy lines the wizard shows next to a purpose (for example "Daily cap: 400") are suggestions. Nothing applies them for you.

## How an incoming message finds its Solution

Routing runs after the checks that already existed: the per-sender rate limit, STOP and START handling, the allow list and pairing. A STOP, START or pairing message never creates or refreshes a pin.

For every other message Huf tries these steps in order and stops at the first that matches:

1. Referral: a Click-to-WhatsApp ad id or a `ref:<tag>` token that matches an "Ad or link tag" entry point. A template quick-reply button whose payload starts with `sol:<solution>` also routes here.
2. Triage answer: the customer answers an open triage menu with its number.
3. Pin: the chat is already pinned to a live Solution. If the number setting "Keyword beats pin" is on, a keyword that belongs to a different Solution wins over the pin.
4. Keyword: a Keyword entry point whose word appears in the message (see [Keyword](#keyword)).
5. Catch-all entry point.
6. The number's older rules (match types such as Any conversation, Direct message, Sender). These are still evaluated, in priority order.
7. The number's default agent or flow. This is a number-level answer, not a Solution, so it does not pin the chat.
8. The triage menu, if the number has a Triage entry point.
9. Nothing matches: the message is recorded and gets no reply.

Paused Solutions and Solutions in test mode are skipped at every step.

The Test chat tab of a Solution runs the same decision without sending anything and prints the reason for each step it took, so you can check a rule before it takes live traffic.

## Entry points

Each entry point is a rule on one number that points at one Solution. An entry point can also carry its own daily cap and recipient scope (see [Limits](#limits-and-the-numbers-ceiling)).

### Keyword

A comma-separated list of words. The rule matches when any word appears anywhere in the message, ignoring case ("cake" matches "Do you have CAKES?"). Rules are checked in priority order.

### Ad tag and link tag

An "Ad or link tag" entry point holds one or more tags. Huf reads the tag from the incoming message in this order:

1. The `source_id` of a Click-to-WhatsApp ad (Meta sends it in the message's `referral` block). Use the ad's id as the tag.
2. The first `ref:<tag>` token in the message text, for example `ref:weekend_special`. The tag may use letters, digits, `_` and `-`, up to 64 characters, and `ref:` is not case-sensitive. The token stays in the message text.

A hash tag such as `#weekend` is not a tag. Tags match whole, ignoring case. For a click-to-chat link or a QR code, put the token in the prefilled text, for example `https://wa.me/<number>?text=Hi%20ref:weekend_special`.

### Catch-all

Receives every message that no earlier step claimed. If a number has several, the one with the lowest priority number wins.

### Triage menu

A Triage entry point makes Huf ask the customer which Solution they want, when nothing else matched and the number has no default agent or flow. The menu lists every live Solution that has an enabled entry point on the number, sorted by title:

```
Hi, this is us. Reply:
1 for Catering bookings
2 for Order desk
```

- The menu is plain text and written by Huf. No model writes it, and it uses no buttons.
- The customer answers `1`, `1.` or ` 1 `. Anything else is treated as a normal message and goes through routing again. The answer is accepted for 30 minutes after the menu was sent.
- The menu is sent at most once per incoming message, even if the same webhook is delivered twice or an event is replayed. It is not sent to a contact who has opted out.
- The answer pins the chat to the chosen Solution.

## Conversation pin

When a message is routed to a Solution, Huf pins the chat (this number and this contact, or the group id for a group chat) to that Solution. Later messages go to the same Solution without any rule being checked. This keeps a long conversation with one agent even when the customer's words stop matching a keyword.

- The pin lasts 24 hours by default. The number setting "Pin hours" changes this.
- Every message that is routed to a Solution refreshes the pin to the full time again, so it expires after the chat has been quiet for that long.
- After the pin expires, routing starts from the top of the list again.
- A message answered by the number's default agent or flow, or by nothing, does not create or refresh a pin.
- A hand-off (see below) replaces the pin.

### Sticky pin or keyword wins

By default a pinned chat is sticky: a keyword that belongs to another Solution does not move it. Turn on "Keyword beats pin" on the number to let a keyword override the pin; the chat then moves to the keyword's Solution and is pinned there.

## Paused and test mode

| State | Receives live messages | Notes |
|-------|------------------------|-------|
| Live | Yes | |
| Paused | No | Its entry points are skipped and an existing pin to it is ignored. Resume it to go back to Live. |
| Test mode | No | Test mode keeps the Solution Paused. Use the Test chat tab to try it. Going live clears test mode in the same step. |

A Solution is created Paused. Going live needs an answering agent or flow and at least one enabled entry point (a Solution with the "Send updates" purpose needs no entry point). Deleting the last entry point of a Live Solution is refused: pause it first.

The Test chat tab includes Paused and test mode Solutions so you can try them before they take traffic. The test chat never writes a pin or sends a message.

## Templates

Message templates are shared at the WhatsApp account level: a template belongs to a name and language on the account, not to one Solution. Huf records which Solutions use each template.

- A Solution uses a template when it declares it (in the wizard, or through the `declare_template_usage` API) or when it sends it. The first Solution to use a template becomes its owner. Others are users.
- The Templates list can be filtered by Solution, and shows the Solutions that use each template and a Shared label when more than one does.
- Editing or deleting a template that several Solutions use is stopped with a warning that lists them. You can edit or delete it for everyone, make a copy, or cancel. A copy lets you change the wording without touching the other Solutions. An edit goes back to Meta review, so every Solution that uses the template is affected until it is approved again.
- A Solution's Templates tab shows only its own templates.

## Limits and the number's ceiling

An entry point can set a daily cap and a recipient scope for its Solution:

- "Daily messages it may start" (the daily cap): the most messages that Solution's agent may send per 24 hours.
- "Who it may message" (the recipient scope): "Same as the number", or a narrower choice, "Only approved contacts" or "Allow list".

Entry point limits can only tighten the number's limits. Huf refuses to save a cap above the number's ceiling and a scope wider than the number's own recipient scope. At send time the stricter value of the two applies.

### What the ceiling is

The ceiling is the most the number can send per day:

1. Meta's messaging limit tier for the number (for example 1,000 or 10,000 business-initiated conversations a day), when Huf's last token check reported it. Huf reads the cached result of the token check and never calls Meta from the Solutions screens. An unlimited tier means there is no ceiling.
2. Otherwise the number's own "agent send cap per day", if it is above zero.
3. Otherwise there is no ceiling. The cap slider is not locked.

The Solution pages show which one is in force. The usage percentage is the Solution's sends in the last 24 hours divided by the ceiling. It is a guide: it counts messages, and Meta's tier is Meta's own measure.

### What is counted

Caps and usage count the messages an agent sends through the WhatsApp tool (they are recorded as send keys). Replies Huf sends automatically to an incoming message are not part of these counts. The number's existing per-run and per-day agent caps keep applying; a Solution's cap is one more check on top.

### Health and "most sends"

The number's health band names the Solution with the largest share of the last 24 hours of sends, worded as "most sends", not as the cause of a problem. The quality rating is shown only when the token check returned one; otherwise it reads as unknown.

## Message log

The Messages tab of the number has a Solution column and a Solution filter. A message is attributed through the send record, the gateway event or the agent run that produced it. Messages that none of them link to show no Solution, which includes messages sent before Solutions were set up.

## Handing a chat to another Solution

An agent can hand the current chat to another Solution with the built-in tool `handoff_to_solution` (category Communication Tools; add it to the agent's tools).

| Argument | |
|----------|---|
| `solution` | Name or title of a Live Solution. Required. |
| `reason` | A short reason. Optional. |

- It works only inside a WhatsApp or other gateway conversation. The chat is taken from the current run, never from an argument.
- It changes the pin and sends no message. The agent should tell the customer in its own reply. The customer's next message goes to the new Solution.
- The target must be Live and not in test mode.
- Each Solution keeps its own conversation history. The tool does not copy history across.

The same handoff is available as the API `huf.ai.solutions.handoff.reassign_conversation` (also available from `huf.ai.solutions.crud`), which can additionally drop the last messages (up to 20) of the old Solution's conversation into the new Solution's conversation as one system note. The Test chat tab has a hand-off button.

## Set up two jobs on one number

Example: a bakery number that takes orders and answers catering enquiries.

1. Connect the number under WhatsApp. Check that its Overview shows a healthy token.
2. Open Solutions and choose New solution.
3. Step 1: name it "Order desk". Pick the purpose "Take orders". Under Runs on, choose the number. Under "Answered by", pick the agent or flow that should reply (you can also choose it later; until then the Solution stays Paused).
4. Step 2: keep the suggested keywords (order, menu, cake) or change them. Add an ad tag if you run a Click-to-WhatsApp ad, using the ad id.
5. Step 3: pick the suggested templates, reuse templates that already exist, or start a draft. Templates other Solutions use are marked Shared.
6. Step 4: try messages in the test chat, for example "I want to order a cake". Then choose Go live.
7. Repeat for "Catering bookings": purpose "Bookings", keywords such as book, event, quote, catering, and the ad tag from the catering ad.
8. Add a Triage entry point on one of them if you want the menu for anyone who matches neither. Without a Triage entry point or a default agent, a message that matches nothing gets no reply.
9. Open the number's Overview. "Solutions on this number" lists both jobs with their usage, and "Routing order" shows the order the entry points are tried in.
10. Check the result in the Test chat tab: a message with "quote" goes to Catering bookings, "menu" goes to Order desk, and once a chat is pinned, a later message goes to the same Solution even when it matches nothing.

Tip: if the two jobs share words, decide whether a pinned chat should stay put or follow the keyword and set "Keyword beats pin" on the number to match.

## Known limits

- The entry point checkbox "May message customers first (templates only)" is stored with the entry point but not yet enforced.
- Groups are not supported. See [WhatsApp in Huf](whatsapp/README.md#limitations).
- Messages routed by the number's default agent or flow, or by older routing rules, are not attributed to a Solution. They show no Solution in the log.
- Flow runs are not stamped with the Solution; the Solution is recorded on the gateway event.
- A template reply button only routes to a Solution if its payload has the form `sol:<solution>|<free text>`. Huf's template sender does not support quick-reply buttons yet, so it cannot add that payload; only payloads set elsewhere route this way.
- A Solution needs an answering agent or flow to go live. The wizard's "Answered by" picker is optional in every mode: a Solution saved without one stays Paused and shows a "Choose what answers" card on its page until you pick one.
- The triage menu opens with "Hi, this is us." The wording is fixed.
