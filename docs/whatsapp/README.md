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

Notes:

- The guide describes the behaviour of the `pre-develop` branch as of October 2026. Every concrete claim was checked against the code (see the file map in the appendix).
- The screenshots are of the real Huf console run against mocked data for a fictional bakery (fictional `+1 555 01xx` numbers). Where no screenshot exists, the guide draws a labelled illustration.
- The guide is generated (HTML rendered to PDF with weasyprint); its source and build script are kept in the workspace track `RepoStructure/ongoing3/build`, not in this repository.
