# Running local models (Ollama / LM Studio)

Huf can run agents against models hosted on your own machine or network — [Ollama](https://ollama.com), [LM Studio](https://lmstudio.ai), or any OpenAI-compatible endpoint — with no cloud API key. Chat, streaming, tool calling, multi-turn memory, and title generation all work against local models. This page covers setup, the Docker networking caveats, model naming rules, and the errors you are most likely to hit.

Local-provider behavior in Huf follows a simple precedence rule for where requests are sent: the provider's **API Base URL** field wins, then the `OLLAMA_API_BASE` environment variable (Ollama brand only), then LiteLLM's built-in default of `http://localhost:11434`. You should almost always use the field; the env var exists for backward compatibility and must be set for *every* bench process (web, workers, scheduler) to be reliable.

## Prerequisites

- Ollama installed and serving (`ollama serve`, or the desktop app) with at least one model pulled: `ollama pull gemma4:latest` or `ollama pull gpt-oss:20b`.
- If Huf runs in Docker (the standard `frappe_docker` devcontainer or production compose), Ollama on the host is **not** reachable at `localhost` from inside the container — see the Docker section below.
- A Huf bench where you can create AI Provider, AI Model, and Agent records (System Manager role, or the Huf UI's Providers/Models/Agents pages).

## Adding a local provider (UI)

On the **Providers** page, open **Add Provider**:

1. **Provider Name** — a single word, no spaces. This name becomes the LiteLLM model prefix; `Ollama Local` (with a space) produces the invalid prefix `ollama local/…` and every request fails with `LLM Provider NOT provided`. Use `Ollama`.
2. **Provider Brand** — `ollama` for Ollama, `lmstudio` for LM Studio, `other` for any other OpenAI-compatible server.
3. **Local / self-hosted endpoint** (`is_local_llm`) — check this. It tells Huf to resolve a custom base URL and to relax cloud-provider assumptions.
4. **API Base URL** (`api_base_url`) — shown once the local checkbox is on, e.g. `http://host.docker.internal:11434` for Ollama on the host from Docker, or `http://192.168.1.20:11434` for Ollama on another LAN machine.
5. **API Key** — optional for local providers. Ollama and LM Studio ignore it; leave it empty and Huf stores a placeholder. (Cloud brands still require a real key.)

Save, then use the **Test Connection** button on the provider's Configure dialog. For Ollama this probes `{api_base_url}/api/tags` and then checks each linked AI Model against `/api/show`, reporting per-model `ok`, capabilities (`tools`, `vision`, `thinking`), or the exact error. Misconfiguration is discovered here, not mid-chat.

## Docker: reaching Ollama on the host

Inside a container, `localhost` is the container itself. The working configurations:

- **Docker Desktop (macOS/Windows)**: use `http://host.docker.internal:11434` as the API Base URL. Ollama's default `127.0.0.1` bind on the host works fine with this.
- **Linux (docker bridge network)**: `host.docker.internal` does not resolve by default. Either use the host's bridge-gateway IP `http://172.17.0.1:11434`, or add `extra_hosts: ["host.docker.internal:host-gateway"]` to the service in your compose file and use `host.docker.internal`. Ollama must also listen on more than loopback: start it with `OLLAMA_HOST=0.0.0.0 ollama serve` (or set the `OLLAMA_HOST` environment variable for the service) so it accepts connections from the docker bridge.
- **Ollama in the same compose project**: use the service name, e.g. `http://ollama:11434`.

The legacy alternative is the `OLLAMA_API_BASE` environment variable. It only applies to the `ollama` brand and must be exported for every bench process (`OLLAMA_API_BASE=http://host.docker.internal:11434 bench start`); workers and the scheduler do not inherit a web-only export. Prefer the field.

## Model naming and the `ollama/` vs `ollama_chat/` prefix

Huf normalizes model names to LiteLLM's `provider/model` format. If the model name already contains a `/`, it is used verbatim; otherwise the provider brand supplies the prefix. For the `ollama` brand, Huf routes through `ollama_chat/` automatically — so a model entered as `gpt-oss:20b` on an `Ollama` provider is served as `ollama_chat/gpt-oss:20b`.

The distinction matters because of a known LiteLLM behavior: **reasoning models such as `gpt-oss` return empty responses via the `ollama/` endpoint whenever tools are attached**, and Huf always attaches its internal tools. The same payload via `ollama_chat/` works, with reasoning correctly separated into `reasoning_content`. Consequences:

- Enter model names **without** a prefix (`gpt-oss:20b`, `gemma4:latest`) and let the brand mapping route them — you get `ollama_chat/` and reasoning models work.
- If you do write a prefix yourself, use `ollama_chat/…` for reasoning models. `ollama/gemma4:latest` is fine for non-reasoning models.
- Match the tag exactly as `ollama list` shows it; `ollama pull gpt-oss:20b` and `gpt-oss:latest` are different models.

## Agents: enable chat

Set **Allow Chat** (`allow_chat`) on the Agent, otherwise the chat UI and stream endpoint refuse with "does not allow chat/streaming". It defaults off; the agent form shows an inline hint when it is unchecked.

Cost telemetry for local models is recorded as `0` — LiteLLM has no pricing for them and Huf does not invent numbers; token counts on the Agent Run are the usage signal.

## LM Studio (OpenAI-compatible)

LM Studio serves an OpenAI-compatible API at `http://<host>:1234/v1` (default port 1234, enable "Serve on local network" in LM Studio if Huf is in Docker). Setup:

- Provider brand `lmstudio` (mapped to the `openai/` LiteLLM prefix), local checkbox on, API Base URL `http://host.docker.internal:1234/v1` — **include the `/v1`**.
- Model names must match the identifiers LM Studio shows in its server tab (e.g. `qwen2.5-7b-instruct`); they are routed as `openai/<identifier>` to your base URL. If you write the prefix yourself, use `openai/…`.
- API key optional.

The same recipe works for any other OpenAI-compatible server (LocalAI, vLLM, text-generation-webui): brand `other`, local checkbox, the server's `/v1` base URL, `openai/…` model naming.

## Troubleshooting

Failures against local providers surface honestly: the Agent Run is marked **Failed** with an `error_message`, the API returns `success: false`, and the chat shows an error card — never an error string disguised as an assistant reply. What each message means:

| Error message | Cause | Fix |
|---|---|---|
| `Model 'ollama/…' returned an empty response (known with reasoning models on the 'ollama/' endpoint; use the 'ollama_chat/' prefix)` | Reasoning model (e.g. gpt-oss) called through `ollama/` with tools attached returns empty content. | Remove the explicit `ollama/` prefix from the model name and let the `ollama` brand auto-route to `ollama_chat/`, or rename the model to `ollama_chat/<model>`. |
| `litellm.APIConnectionError: … Connection refused` | Nothing is listening at the resolved base URL: Ollama not running, wrong host/port, or `localhost` used from inside a container. | Click **Test Connection** on the provider. Start Ollama (`ollama serve`). From Docker use `host.docker.internal:11434` (Mac/Windows) or `172.17.0.1`/host-gateway (Linux). Verify with `curl http://<base>/api/tags` from inside the container. Transient refusals during an Ollama restart are retried automatically (up to 2 retries). |
| `model '<name>' not found, try pulling it first` | The model tag is not pulled on that Ollama instance. | `ollama pull <name:tag>` with the exact tag from `ollama list`. Test Connection reports this per linked model. |
| `LLM Provider NOT provided` | Provider name contains spaces (e.g. `Ollama Local`), producing an invalid LiteLLM prefix like `ollama local/…`. | Rename the provider to a single word (`Ollama`). Validation now rejects whitespace in provider names at save time. |
| `… does not support tools` / HTTP 400 mentioning tools or `get_result_context` | The model was called with tools but has no tool-calling capability (check with `ollama show <model>`). | Use a tools-capable model (gemma4, gpt-oss, qwen3, llama3.1+). For local providers Huf probes capabilities and strips tools with a logged warning instead of letting the provider fail cryptically — but the agent then cannot use tools at all, so prefer a capable model. |
| `This agent does not allow chat/streaming` | `allow_chat` is off on the Agent. | Enable **Allow Chat** on the agent form. |
| `Failed to create provider` (generic toast) when saving with an empty API key | Older behavior: API key was mandatory for all brands. | On current builds, local providers accept an empty key; the toast now shows the backend's actual validation message if creation still fails. |
| Chat replies wrapped in raw JSON like `{"answer": …}` | Model-side formatting quirk (seen with gemma4 mimicking tool-result JSON). | Cosmetic only — the chat renderer unwraps single-key `answer`/`condensed_answer`/`response` JSON for display. Stored content is unchanged. |

Two limitations to be aware of, unrelated to setup correctness: HTTP tools pointing at private/LAN addresses (`host.docker.internal`, `192.168.*`, …) are blocked by Huf's SSRF guard with "Requests to private/internal addresses are not allowed" — there is no allowlist yet, so agents on local models cannot call local HTTP tools. And running several chats in parallel against the *same* agent can hit a write race on the Agent record; spread load across agents or retry if you see `Record has changed since last read in table 'tabAgent'`.

## See also

- `docs/queue-first-agent-runs.md` — how agent runs are queued and executed; relevant for long local-model generations.
