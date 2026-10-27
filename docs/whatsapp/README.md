# WhatsApp in Huf

[**WhatsApp-in-Huf.pdf**](WhatsApp-in-Huf.pdf) is a 60-page product guide to everything Huf does with WhatsApp: what you can build, how a message travels through Huf, and how each feature works, with screenshots of the console and eight worked use cases.

What it covers:

- **Connecting a number:** setup, credentials, token health, webhooks, several numbers on one site.
- **Who can talk to your agent:** allow list, pairing approvals, opt-out, run-as user.
- **Everything customers can send:** text, voice notes, images, documents, location, contacts, buttons and lists, reactions, edits, ad referrals.
- **Voice and audio in depth:** speech-to-text for voice notes, voice replies (Off / Voice only / Text and voice), the ffmpeg and Opus requirements.
- **Outbound:** formatting, media, interactive messages, templates (wizard, categories, guard, lifecycle), the 24-hour window and outbound policy, idempotent sends.
- **Operating it:** message log and delivery states, drafts, health, the agent tool, flows, reliability and security.
- **Eight use cases:** order-taking, appointments and reminders, support triage with pairing approval, an internal ops bot, field reporting, lead qualification, collections reminders, a voice-first customer.
- **Limitations:** what is not supported today (groups, coexistence, embedded signup, a human inbox, calling beyond an experimental greeting).

## Solutions: several jobs on one number

One number can do several jobs, for example taking orders and answering catering questions. Each job is a Solution with its own agent or flow, entry points, templates and limits. See [Solutions](../solutions.md) for how incoming messages find their Solution, the 24-hour conversation pin, templates shared between Solutions, limits and the number's ceiling, and how to set up two jobs on one number.

### Ad and link tags (referral convention)

To route a customer who arrives from an ad or a link to a particular Solution, use an "Ad or link tag" entry point. Huf reads the tag from the incoming message in this order:

1. The ad id of a Click-to-WhatsApp ad: Meta sends it as `referral.source_id` on the first message. Use that id as the tag.
2. The first `ref:<tag>` token in the message text, for example `ref:weekend_special` (letters, digits, `_` and `-`, up to 64 characters, not case-sensitive). Put it in the prefilled text of a `wa.me` link or QR code.

A `#tag` in the text is not read as a tag.

## Limitations

- **WhatsApp groups are not supported.** Huf does not implement Meta's Groups API yet. Why:
  - Meta's Groups API is available only to Official Business Accounts, and Meta grants it per phone number.
  - Groups are invite-link only and hold at most 8 participants.
  - Group messages cannot be interactive (no buttons or lists), so Huf's menus and buttons would not work in them.
  - Huf has no group support yet: no group creation, invite links, group webhooks or group sends.
  Meta's documentation: <https://developers.facebook.com/documentation/business-messaging/whatsapp/groups>.
- The PDF guide lists the other limitations: coexistence, embedded signup, a human inbox, and calling beyond an experimental greeting.

Notes:

- The guide describes the behaviour of the `pre-develop` branch as of October 2026. Every concrete claim was checked against the code (see the file map in the appendix).
- The screenshots are of the real Huf console run against mocked data for a fictional bakery (fictional `+1 555 01xx` numbers). Where no screenshot exists, the guide draws a labelled illustration.
- The guide is generated (HTML rendered to PDF with weasyprint); its source and build script are kept in the workspace track `RepoStructure/ongoing3/build`, not in this repository.
