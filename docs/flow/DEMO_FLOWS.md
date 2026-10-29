# Huf Demo flows

Twelve ready-made flows, all in the category **Huf Demo** (filter the Flows list by it). Each has a description on its card. Names start with `Huf Demo -`. Open one, read its steps, press **Run** (header) to try it and open **Runs** to see what happened. Nothing here needs code. See [USER_GUIDE.md](USER_GUIDE.md) for every trigger and step.

| Flow | State | What it shows | How to try it |
|---|---|---|---|
| Huf Demo - Webhook basics | Published | Webhook, Transform, End | Open the Webhook step, copy the curl command, add `-H 'Content-Type: application/json' -d '{"name":"ada"}'`, run it in a terminal, then open Runs: the result is ADA. |
| Huf Demo - Condition branching | Draft | Condition with True and False paths | Run with `{"amount": 150}` (path "Big order"), then `{"amount": 50}` ("Small order"). |
| Huf Demo - Loop with collect | Draft | Loop, items collected into a list | Run with `{"items": ["alpha","beta","gamma"]}`: ALPHA, BETA, GAMMA are collected. |
| Huf Demo - Transform ops | Draft | Trim, upper-case, filter rows, sum | Run with `{"name": "  ada lovelace ", "orders": [{"amount": 50}, {"amount": 150}, {"amount": 300}]}`: ADA LOVELACE and a total of 450. |
| Huf Demo - Run Agent | Draft | An AI agent (agent "Huf Demo Agent", OpenAI) inside a flow | Run with `{"name": "Ada"}`: the agent replies with one friendly sentence. Uses your OpenAI key. |
| Huf Demo - LLM Router | Draft | An AI model picks the path | Run with `{"text": "The server is down, customers cannot pay!"}` (urgent: Escalate, then Log request) and `{"text": "Please update my address."}` (routine: straight to Log request). |
| Huf Demo - Human approval | Draft | Pause for a person: Approved and Rejected paths | Run with `{"amount": 42}`. The run waits. Open the bell at the top, or Runs and the run, and Approve or Reject. Approvers: people with the Huf User role (the Administrator has every role). |
| Huf Demo - HTTP Request | Draft | HTTP request to https://example.com | Run with `{}`: the step reads "200 from example.com" and the raw response is folded underneath. |
| Huf Demo - Slack post | Draft | Posts to the Slack channel #huf-live-test | Run once to post a test message. Needs Slack connected in Integrations. |
| Huf Demo - Email | Draft | Sends an email | Change the To address to your own, then Run. Needs Gmail connected in Integrations. |
| Huf Demo - Schedule | Draft | Schedule trigger, every hour | Publish to start; Unpublish to stop. The first run happens at the next full hour. |
| Huf Demo - Data trigger ToDo | Draft | Data trigger on ToDo created | Publish, then create a ToDo in the Desk: a run appears under Runs with the description in capital letters. Unpublish to stop. |

"Huf Demo - Execute Code" is a separate demo of the Execute code step.

Tips: a **Draft** flow only runs when you press Run. **Published** flows are started by their trigger. Keep the demo flows, they are small and safe; delete a flow from its Settings dialog when you no longer want it.
