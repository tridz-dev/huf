# Agent API Features

This document details new features added to the Agent API: **Guest Access** and **Structured Outputs**.

## 1. Guest Access

### Purpose
To enable external applications or users without system accounts to interact with specific Agents. This is useful for public-facing chatbots or integrations.

### Configuration
1. Go to the **Agent** DocType.
2. Under the **Permissions** tab, check the **Allow Guest** box.

### Usage
When enabled, Guest users can call `huf.ai.agent_integration.run_agent_sync` without logging in.

- **Endpoint:** `huf.ai.agent_integration.run_agent_sync`
- **Method:** `POST`
- **Params:** `agent_name`, `prompt`, ...

**Security Note:** Only enable this for Agents that are safe for public use. The Agent will still run with its configured permissions, but the *caller* does not need to be a system user.

---

## 2. Structured Outputs (JSON Mode)

### Purpose
To ensure the Agent returns data in a predictable, machine-readable JSON format, enabling reliable integration with other systems.

You can now enforce a specific JSON structure for the Agent's response using the `response_format` parameter. This leverages LiteLLM's structured output capabilities (supports OpenAI, Gemini, etc.).

### Usage

Pass the `response_format` parameter to `run_agent_sync`. This parameter accepts a JSON Schema definition (or a dict equivalent).

#### Example (Python Request)

```python
import requests
import json

url = "https://your-site.com/api/method/huf.ai.agent_integration.run_agent_sync"

schema = {
  "type": "json_schema",
  "json_schema": {
    "name": "calendar_event",
    "strict": True,
    "schema": {
      "type": "object",
      "properties": {
        "name": {"type": "string"},
        "date": {"type": "string"},
        "participants": {"type": "array", "items": {"type": "string"}}
      },
      "required": ["name", "date", "participants"],
      "additionalProperties": False
    }
  }
}

payload = {
    "agent_name": "MySchedulerAgent",
    "prompt": "Schedule a meeting with Alice and Bob on Friday.",
    "response_format": json.dumps(schema) # Pass as string or JSON object
}

response = requests.post(url, json=payload)
print(response.json())
```

### Supported Models
Ensure your selected Provider/Model supports structured outputs (e.g., `gpt-4o`, `gemini-1.5-pro`).

### Response
The API response will contain:
- `response`: The raw JSON string returned by the model.
- `structured`: A parsed JSON object (if parsing was successful).
