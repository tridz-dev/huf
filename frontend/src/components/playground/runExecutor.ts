import { runAgentSync, runPromptSync } from '@/services/consoleApi';
import type { RunPromptSyncParams, RunPromptSyncResult } from '@/services/consoleApi';
import { db } from '@/lib/frappe-sdk';
import { doctype } from '@/data/doctypes';
import type { AgentRunDoc } from '@/services/agentRunApi';
import type { PlaygroundConfig, RunOutcome } from './types';

/**
 * Telemetry fields the direct-run endpoint is expected to return. Declared
 * locally (instead of on `RunPromptSyncResult`, which is owned elsewhere) so
 * the playground degrades gracefully when they're absent.
 */
interface DirectRunTelemetry {
  latency_ms?: number;
  input_tokens?: number;
  output_tokens?: number;
  cost?: number;
}

interface AgentRunTelemetry {
  latencyMs?: number;
  inputTokens?: number;
  outputTokens?: number;
  cost?: number;
}

function parseOptionalNumber(raw: string): number | undefined {
  const trimmed = raw.trim();
  if (!trimmed) return undefined;
  const value = Number(trimmed);
  return Number.isFinite(value) ? value : undefined;
}

async function fetchAgentRunTelemetry(agentRunId: string): Promise<AgentRunTelemetry> {
  const doc = (await db.getDoc(doctype['Agent Run'], agentRunId)) as AgentRunDoc;
  const telemetry: AgentRunTelemetry = {
    inputTokens: doc.input_tokens ?? undefined,
    outputTokens: doc.output_tokens ?? undefined,
    cost: doc.cost ?? undefined,
  };
  if (doc.start_time && doc.end_time) {
    const start = new Date(doc.start_time).getTime();
    const end = new Date(doc.end_time).getTime();
    if (Number.isFinite(start) && Number.isFinite(end) && end >= start) {
      telemetry.latencyMs = end - start;
    }
  }
  return telemetry;
}

/**
 * Execute one bench run against the given config. Agent runs measure latency
 * client-side and enrich from the Agent Run doc; direct runs read telemetry
 * from the endpoint response (falling back to client-measured latency).
 */
export async function executeRun(config: PlaygroundConfig): Promise<RunOutcome> {
  const startedAt = performance.now();

  if (config.agentName) {
    const result = await runAgentSync({
      agent_name: config.agentName,
      prompt: config.prompt.trim(),
      provider: config.provider,
      model: config.model,
      now: true,
    });
    const clientLatencyMs = performance.now() - startedAt;

    let telemetry: AgentRunTelemetry = {};
    if (result.agent_run_id) {
      try {
        telemetry = await fetchAgentRunTelemetry(result.agent_run_id);
      } catch {
        // Telemetry enrichment is best-effort; latency + model still render.
      }
    }

    return {
      success: result.success,
      response: result.response,
      error: result.error,
      latencyMs: telemetry.latencyMs ?? clientLatencyMs,
      inputTokens: telemetry.inputTokens,
      outputTokens: telemetry.outputTokens,
      cost: telemetry.cost,
      model: config.model,
      agentRunId: result.agent_run_id,
    };
  }

  const params = {
    provider: config.provider,
    model: config.model,
    prompt: config.prompt.trim(),
    temperature: parseOptionalNumber(config.temperature),
    maxTokens: parseOptionalNumber(config.maxTokens),
  } as RunPromptSyncParams;

  const result = (await runPromptSync(params)) as RunPromptSyncResult & DirectRunTelemetry;
  const clientLatencyMs = performance.now() - startedAt;

  return {
    success: result.success,
    response: result.response,
    error: result.error,
    latencyMs: result.latency_ms ?? clientLatencyMs,
    inputTokens: result.input_tokens,
    outputTokens: result.output_tokens,
    cost: result.cost,
    model: result.model ?? config.model,
  };
}
