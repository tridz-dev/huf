# Flows: user guide

A flow starts from a **trigger** and then runs **steps** one after another. Each step can use the result of the steps before it. You build a flow on a canvas: choose a trigger, add steps, connect them, then **Save**, **Run** it once to try it and **Publish** it so its trigger starts it by itself.

## The 3-step start

1. Choose what starts the flow (the trigger).
2. Add steps (click **Add step** under the last step).
3. Save, then Run (one test run now) or Publish (turn the trigger on).

The **?** button in the editor header repeats this and lists the keyboard shortcuts.

## Header buttons

| Button | What it does |
|---|---|
| Save | Saves your changes (Ctrl/Cmd+S). A flow with a missing field cannot be saved; the step is selected and says what is missing. |
| Runs | Run history of this flow, newest first. Select a run to see what each step did. |
| Settings | Name, description and category. Delete the flow here. |
| Run | Starts one real run now with input data you type (JSON). Emails are sent and records are created. |
| Publish | Turns the trigger on: the webhook accepts calls, a schedule or record change starts runs. |
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

- Fields: URL (read only), Secret, Method (POST or GET).
- The caller sends the secret in the `X-Huf-Secret` header. A flow must be published to accept calls.
- Example: `curl -X POST -H "X-Huf-Secret: <secret>" -H "Content-Type: application/json" -d '{"name":"Ada"}' "<url>"`
- Answers: 200 started (the answer holds the run id), 403 wrong or missing secret or not published, 405 wrong method, 429 more than 60 calls a minute.
- Common errors: calling with `?secret=` in the address (not accepted, use the header); flow not published; method differs from the one chosen.

### Schedule

Starts the flow by itself at times you choose, while the flow is published.

- Fields: How often (every few minutes or hours, every day, week or month, or a custom cron expression).
- Times use the site's time zone, which the editor shows under the schedule. Run history shows times in your browser's time zone, so they can differ.
- Cron has five parts: minute, hour, day of month, month, day of week. `*/15 * * * *` is every 15 minutes; `0 9 * * 1-5` is weekdays at 09:00.
- Common errors: a cron with a number out of range (for example hour 25); forgetting to publish.

### Data

Starts the flow when a record changes, for example when a ToDo is created.

- Fields: Document type, When it fires (created, updated, submitted, cancelled, deleted).
- Submit and cancel only exist for document types that can be submitted.
- The record's fields are available as `input['field']`.
- Common errors: choosing an event the document type never fires; forgetting to publish.

## Steps

### Run agent

Asks one of your AI agents to do a task; its reply goes to the next step.

- Fields: Agent, Prompt (use `{name}` or Insert data to include data).
- Example prompt: `Summarise this support ticket in two sentences: {ticket}`
- Common errors: no agent chosen; the agent's AI provider has no working key (the step fails with a message naming the provider).

### Call tool

Runs one tool (built in or from a connected server). Pick the tool, then fill its fields.

- Optional "Wait up to" applies to tools from connected servers.
- Common errors: required field empty; tool needs an integration that is not connected.

### HTTP Request

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

### File operations

Lists, searches or reads files in Google Drive. Common errors: Google Drive not connected; missing file ID.

### Condition (If/Else)

Sends the flow down the **True** or **False** path.

- Field: Condition, a check that is true or false.
- Syntax: read trigger data as `input['field']`; compare with `==`, `!=`, `>`, `>=`, `<`, `<=`, `in`; combine with `and`, `or`, `not`. Text needs quotes.
- Examples: `input['amount'] > 100`, `input['status'] == 'paid'`, `input['country'] in ['IN', 'US']`, `input['vip'] and input['total'] >= 500`.
- Common errors: missing quotes around text; one of the two paths not connected.

### LLM Router

Lets an AI model choose the next step.

- Fields: How should the AI choose? (a question), AI model (optional), Paths (one named arrow per possible next step), If nothing matches (a default path).
- Name the paths clearly, for example `urgent` and `routine`; the AI picks the one whose name fits.
- Common errors: a path without a name; no default path; the provider has no working key.

### Loop

Repeats the steps on the **For each item** path once for every item of a list, then continues on **When done**.

- Fields: List to loop over (for example `input.recipients`), Maximum items (a safety limit: a longer list fails the loop), If one item fails (stop the flow or skip that item), Result to collect (added to a list handed to the next step).
- Common errors: the list field is not a list; the list is longer than the maximum.

### Human in Loop

Pauses until a person approves or rejects. **Approved**, **Rejected** and (when a time limit is set) **Timed out** are separate paths.

- Fields: Message for the approver, Who can approve (a role, or specific people by email), Give up after (minutes).
- Approvers see waiting requests in the bell menu and in the run's details. The first answer counts.
- If nobody answers in time the flow follows the Timed out path; without that path the run fails.
- Common errors: approver not chosen; the person answering has not the role.

### Transform data

Changes data without AI. Pick an operation; each shows a one-line description and an example.

| Operation | What it does | Example |
|---|---|---|
| Lowercase / Uppercase | Changes letter case | "Hello" gives "hello" |
| Trim whitespace | Removes spaces at both ends | "  Ada  " gives "Ada" |
| Replace text | Replaces part of the text | "a-b" with "-" to " " gives "a b" |
| Contains / Starts with | True or false check on text | "INV-1" starts with "INV-" is true |
| Split (first part) | Keeps the part before the separator | "Ada Lovelace" gives "Ada" |
| Regex extract | First piece matching a pattern | `[0-9]+` on "order 4521" gives "4521" |
| Concatenate | Joins values | ["a","b"] with "-" gives "a-b" |
| Select fields, Filter rows, Sort rows, Limit rows | Work on a list of records | keep rows where `row['amount'] > 100` |
| Group by, Aggregate, Batch, Distinct | Group, count or sum, split in chunks, remove duplicates | sum of "amount" |
| Join, Lookup | Combine two lists | add the customer to each order |
| Coalesce | First value that is not empty | [null, "x"] gives "x" |

Common errors: a required field empty; a list expected but text given.

### Execute code

Runs a short piece of Python in a sandbox and passes what it prints and returns to the next step. The card only appears when your administrator allows code in flows and your role may use it.

- Fields: Python code, How it may run (the sandbox profile), inputs, and a time limit.
- The run details show the exit status (Ok or not), what the code printed and its result. Output that is too long is cut off and says so.
- Common errors: an error in the code (the printed error is in the output); the time limit; the administrator has not approved the code (the run waits for approval).

### Get state, Set state, Delete state

A small memory that belongs to the flow. Set state saves a value under a key (optionally forgetting it after some seconds), Get state reads it (with an optional default), Delete state removes it. Use a template key such as `cart:{sender}` to keep one value per sender.

### Create document

Creates a record of a document type your administrator allowed (for example ToDo). Add one row per field. The new record's details go to the next step. Common errors: document type not allowed; a required field of the record missing.

### End

Finishes the flow and returns an optional result (shown in run details).

## Runs

Select **Runs** in the header for the flow's history, or open **Executions** and the Flow runs tab for every flow. A run shows its status (Queued, Running, Waiting, Success, Failed), the steps that ran with their results, the trigger input and, for a failed run, the step that failed and why. Times are shown in your browser's time zone.

## Keyboard shortcuts

Ctrl/Cmd+S save, Delete or Backspace remove the selected step or connection (asks first), Ctrl/Cmd+Z undo the last removal, Tab move between steps, Enter open the focused Add step card, Esc close a dialog, scroll to zoom, drag the background to move.

## Demo flows

See [DEMO_FLOWS.md](DEMO_FLOWS.md) for ready-made flows you can open and try.
