# Flows: user guide

A flow starts from a **trigger** and then runs **steps** one after another. Each step can use the result of the steps before it. You build a flow on a canvas: choose a trigger, add steps, connect them, then **Save**, **Run** it once to try it and **Publish** it so its trigger starts it by itself.

## The 3-step start

1. Choose what starts the flow (the trigger).
2. Add steps (click **Add step** under the last step).
3. Save, then Run (one test run now) or Publish (turn the trigger on).

The **?** button in the editor header repeats this and lists the keyboard shortcuts.

## The Flows list

Each card shows the flow name (two lines at most; hover for the full name), a plain description (or "Starts when a web request arrives, then 3 steps." when the author wrote none), one status word (**Draft** or **Live**), what starts it, how the **last run** went and how long ago, and the steps as small icons. **Open** edits the flow, **Run** starts it by hand, and the **...** menu has **Duplicate**, **Settings** and **Delete**. Search looks in names, descriptions and categories; the dropdowns filter by status and category and sort.

**New flow** opens a chooser: **Start from scratch**, or a **template** (a ready-made small flow: reply to a web request, split big and small orders, loop over items, ask an AI agent, ask a person to approve, run on a schedule, react to a new record, post to Slack, send an email ...). A template is copied into a NEW draft that is yours: its own name ("... 2" if the name is taken), its own webhook secret, and steps that still need something (a Slack channel, an e-mail address, a connected app) marked "Needs setup". The catalog ships with the app (`frontend/src/data/flowTemplates.json`, made from the Huf Demo flows with site-specific values removed), so it works on any site without a set-up script.

## Header buttons

| Button | What it does |
|---|---|
| Save | Saves your changes (Ctrl/Cmd+S). A flow with a missing field cannot be saved; the step is selected and says what is missing. |
| Runs | Run history of this flow, newest first. Select a run to see what each step did. |
| Settings | Name, description and category; a collapsed **More** (procedure option); and a **Danger zone** to delete the flow (asks "Delete this flow?" in the same dialog). Saving only changes these details, never the steps. |
| Run | Starts one real run now with input data you type (JSON). Emails are sent and records are created. |
| Publish | Asks first: it shows what will start the flow (the web address with a Copy button, "every day at 09:00", "when a ToDo is created") and warns about apps that are not connected or unfinished steps. **Publish** then turns the trigger on. |
| Unpublish | Turns the trigger off. The flow becomes a draft again; runs in progress finish. |

Read-only users can look at flows and runs but cannot save, run or publish.

## Using data from earlier steps

Most fields have an **Insert data** button. It lists the trigger and the steps that always run before this one.

- The trigger's data is called `input`. If a webhook receives `{"name": "Ada"}`, a later step can use `input.name`.
- Each value can be given four ways: **Literal** (typed as is), **Reference** (copy a value from the trigger or an earlier step, for example `input.name`), **Template** (text with `{placeholders}`) or **JSON** (a list or object).
- In a condition, write references like `input['name']`.

## Triggers

### Webhook

Starts the flow when another system sends a request to the flow's web address.

- Fields: how it is called (POST can send data, GET only starts the flow), the secret, the web address (read only, with Copy).
- The secret shows as `****c3e6`. Press Show to see it for 30 seconds, Copy to copy it, "Make a new secret" (after a confirmation) to replace it. People who can only view the flow see "Hidden. Ask a flow editor."
- "Data it sends": press "Paste a sample request" (or "Use last received request") to list the fields the other app sends, so you know what later steps can use. The sample is kept with the flow (small, passwords and keys hidden).
- "How to call this webhook" (closed by default) is for whoever connects the other app: a "Request body (JSON)" example and a ready-to-run command.
- The caller sends the secret in the `X-Huf-Secret` header. A flow must be live (published) to accept calls.
- Example: `curl -X POST -H "X-Huf-Secret: <secret>" -H "Content-Type: application/json" -d '{"name":"Ada"}' "<url>"`
- Answers: 200 started (the answer holds the run id), 403 wrong or missing secret or not published, 405 wrong method, 429 more than 60 calls a minute.
- Common errors: calling with `?secret=` in the address (not accepted, use the header); flow not published; method differs from the one chosen.

### Schedule

Starts the flow by itself at times you choose, while the flow is published.

- Fields: How often (every few minutes or hours, every day, on certain days of the week, every month, or Custom), the time, and the time zone.
- The summary says it in words, for example "Every day at 09:00 in Asia/Kolkata", with the next three runs and how the time shows in your browser. The time zone starts as the site's; change it if the schedule should follow another clock. Run history shows times in your browser's time zone.
- Every few hours counts from midnight (3 hours = 00:00, 03:00, 06:00 ...). Monthly can be day 1 to 31 or the last day of the month; months without that day are skipped.
- Custom takes a five-part pattern (minute, hour, day of month, month, day of week): `*/5 9-17 * * 1-5` is every 5 minutes, 9am to 5pm, Monday to Friday. It only appears under Custom.
- Common errors: a pattern with a number out of range (for example hour 25); forgetting to publish.

### When a document changes (was "Data" / "Record change")

Starts the flow when something is added, changed or deleted in your data, for example when a To-do is created.

- A sentence: "When a [kind of record] is [created]". The list is searchable and leaves out system records. The event starts as "created".
- Events: created, changed, deleted; submitted and cancelled only for document types that can be submitted.
- The details of the record are available to the steps that follow.
- Common errors: choosing an event the document type never fires; forgetting to publish.

## Steps

### Run agent

Asks one of your AI agents to do a task; its reply goes to the next step.

- Fields: Agent, Prompt (use `{name}` or Insert data to include data).
- Example prompt: `Summarise this support ticket in two sentences: {ticket}`
- Common errors: no agent chosen; the agent's AI provider has no working key (the step fails with a message naming the provider).

### Do something in an app (was "Call tool")

Runs one tool (built in or from a connected server). Pick the tool, then fill its fields.

- Optional "Wait up to" applies to tools from connected servers.
- Common errors: required field empty; tool needs an integration that is not connected.

### Web request (was "HTTP Request")

Calls a web address and passes the response to the next step.

- Fields: URL (https://...), Method, Headers (JSON), Body (JSON, for POST, PUT, PATCH).
- Example headers: `{"Authorization": "Bearer your-key"}`
- Common errors: addresses on private networks are blocked; a non-2xx answer is shown in the run details.
- Publishing a flow with a web request needs a permission your administrator grants.

### Send email

Sends an email from your connected Gmail account. Fields: To (several separated by commas), Subject, Body.
Common errors: Gmail not connected (use the Connect link on the step); invalid address.

### Slack

Posts a message to a Slack channel (or replies in a thread). Fields: Channel (name like `#general` or the channel ID), Message.
The bot must be invited to the channel. Common errors: Slack not connected; channel not found.

### Google Sheets

Reads, writes or creates a spreadsheet. Fields depend on the tool: Spreadsheet ID (the text between `/d/` and `/edit` in the sheet's address), Range (`Sheet1!A1:D20`), Data (a list of rows: `[["Name","Amount"],["Ada",120]]`).
Common errors: Google Sheets not connected; missing range.

### Google Drive files (was "File operations")

Lists, searches or reads files in Google Drive. Common errors: Google Drive not connected; missing file ID.

### If / else (was "Condition (If/Else)")

Sends the flow down the **True** or **False** path.

- Field: Condition, a check that is true or false.
- Syntax: read trigger data as `input['field']`; compare with `==`, `!=`, `>`, `>=`, `<`, `<=`, `in`; combine with `and`, `or`, `not`. Text needs quotes.
- Examples: `input['amount'] > 100`, `input['status'] == 'paid'`, `input['country'] in ['IN', 'US']`, `input['vip'] and input['total'] >= 500`.
- Common errors: missing quotes around text; one of the two paths not connected.

### Choose with AI (was "LLM Router")

Lets an AI model choose the next step.

- Fields: How should the AI choose? (a question), AI model (optional), Paths (one named arrow per possible next step), If nothing matches (a default path).
- Name the paths clearly, for example `urgent` and `routine`; the AI picks the one whose name fits.
- Common errors: a path without a name; no default path; the provider has no working key.

### Repeat for each item (was "Loop")

Repeats the steps on the **For each item** path once for every item of a list, then continues on **When done**.

- Fields: List to loop over (for example `input.recipients`), Maximum items (a safety limit: a longer list fails the loop), If one item fails (stop the flow or skip that item), Result to collect (added to a list handed to the next step).
- Common errors: the list field is not a list; the list is longer than the maximum.

### Wait for approval (was "Human in Loop")

Pauses until a person approves or rejects. **Approved**, **Rejected** and (when a time limit is set) **Timed out** are separate paths.

- Fields: Message for the approver, Who can approve (a role, or specific people by email), Give up after (minutes).
- Approvers see waiting requests in the bell menu and in the run's details. The first answer counts.
- If nobody answers in time the flow follows the Timed out path; without that path the run fails.
- Common errors: approver not chosen; the person answering has not the role.

### Change data (was "Transform data")

Changes data without AI. Pick an operation; each shows a one-line description and an example.

| Operation | What it does | Example |
|---|---|---|
| Lowercase / Uppercase | Changes letter case | "Hello" gives "hello" |
| Trim whitespace | Removes spaces at both ends | "  Ada  " gives "Ada" |
| Replace text | Replaces part of the text | "a-b" with "-" to " " gives "a b" |
| Contains / Starts with | True or false check on text | "INV-1" starts with "INV-" is true |
| Split (first part) | Keeps the part before the separator | "Ada Lovelace" gives "Ada" |
| Find with a pattern (regex) | First piece matching a pattern | `[0-9]+` on "order 4521" gives "4521" |
| Join text together | Joins values | ["a","b"] with "-" gives "a-b" |
| Select fields, Filter rows, Sort rows, Limit rows | Work on a list of records | keep rows where `row['amount'] > 100` |
| Group by, Aggregate, Batch, Distinct | Group, count or sum, split in chunks, remove duplicates | sum of "amount" |
| Join, Lookup | Combine two lists | add the customer to each order |
| First value that is not empty | First value that is not empty | [null, "x"] gives "x" |

Common errors: a required field empty; a list expected but text given.

### Run Python code (was "Execute code")

Runs a short piece of Python in a sandbox and passes what it prints and returns to the next step. The card only appears when your administrator allows code in flows and your role may use it.

- Fields: Python code, How it may run (the sandbox profile), inputs, and a time limit.
- The run details show the exit status (Ok or not), what the code printed and its result. Output that is too long is cut off and says so.
- Common errors: an error in the code (the printed error is in the output); the time limit; the administrator has not approved the code (the run waits for approval).

### Save data for later, Look up saved data, Forget saved data

A small memory that belongs to the flow. Set state saves a value under a key (optionally forgetting it after some seconds), Get state reads it (with an optional default), Delete state removes it. Use a template key such as `cart:{sender}` to keep one value per sender.

### Create a record (was "Create document")

Creates a record of a document type your administrator allowed (for example ToDo). Add one row per field. The new record's details go to the next step. Common errors: document type not allowed; a required field of the record missing.

### Finish (was "End")

Finishes the flow and returns an optional result (shown in run details).

## Runs

Select **Runs** in the header for the flow's history, or open **Executions** and the Flow runs tab for every flow. A run shows its status (Queued, Running, Waiting, Success, Failed), the steps that ran with their results, the trigger input and, for a failed run, the step that failed and why. Times are shown in your browser's time zone.

## Keyboard shortcuts

Ctrl/Cmd+S save, Delete or Backspace remove the selected step or connection (asks first), Ctrl/Cmd+Z undo the last removal, Tab move between steps, Enter open the focused Add step card, Esc close a dialog, scroll to zoom, drag the background to move.

## Demo flows

See [DEMO_FLOWS.md](DEMO_FLOWS.md) for ready-made flows you can open and try.
