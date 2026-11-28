import { db } from '@/lib/frappe-sdk';
import { doctype } from '@/data/doctypes';
import { getAgentRunStatus, type AgentRunStatusResponse } from '@/services/chatApi';

/** Gateway statuses that mean "the proxy gave up", not "the server refused the request". */
export const GATEWAY_STATUSES: ReadonlySet<number> = new Set([502, 503, 504]);

/** The stream endpoint answered 502/503/504: the run may still exist and finish on the server. */
export class GatewayError extends Error {
  readonly status: number;
  constructor(status: number) {
    super(`Request failed: ${status}`);
    this.name = 'GatewayError';
    this.status = status;
  }
}

export interface RecoveredRun {
  success: boolean;
  /** True when the run was still Queued/Started at the deadline: the run poller takes over. */
  queued: boolean;
  status: AgentRunStatusResponse['status'];
  response?: string;
  error?: string;
  conversation_id?: string;
  agent_run_id: string;
  agent_message_id?: string;
}

export interface RecoverParams {
  /** Run id when the stream already reported it (`run_started`); otherwise the run is looked up. */
  runId?: string | null;
  conversationId?: string;
  /** Idempotency key the request carried: finds the run even before any conversation is known. */
  clientKey?: string;
  /** Epoch ms the request was sent; only runs created after it (minus slack) are considered. */
  startedAt: number;
  signal?: AbortSignal;
}

export interface RecoverDeps {
  sleep: (ms: number) => Promise<void>;
  now: () => number;
  getStatus: (runId: string) => Promise<AgentRunStatusResponse>;
  findRun: (conversationId: string, sinceMs: number) => Promise<string | null>;
  findByKey: (clientKey: string) => Promise<string | null>;
  pollMs: number;
  findTimeoutMs: number;
  totalTimeoutMs: number;
}

// The chat gives up on a silent turn after 180s: hand an open run to the run poller before that.
const MAX_FROM_SEND_MS = 170_000;

// Server and browser clocks differ; accept runs created slightly before our send time.
// Frappe stores `creation` as a naive timestamp, compared here in browser-local time.
const CLOCK_SLACK_MS = 60_000;

function toFrappeLocal(ms: number): string {
  const d = new Date(ms);
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

async function findLatestRun(conversationId: string, sinceMs: number): Promise<string | null> {
  const since = toFrappeLocal(sinceMs - CLOCK_SLACK_MS);
  const runs = (await db.getDocList(doctype['Agent Run'], {
    fields: ['name'],
    filters: [
      ['conversation', '=', conversationId],
      ['is_child', '=', 0],
      ['creation', '>=', since],
    ],
    orderBy: { field: 'creation', order: 'desc' },
    limit: 1,
  })) as Array<{ name: string }>;
  return runs[0]?.name ?? null;
}

export async function findRunByClientKey(clientKey: string): Promise<string | null> {
  const runs = (await db.getDocList(doctype['Agent Run'], {
    fields: ['name'],
    filters: [['idempotency_key', '=', clientKey]],
    limit: 1,
  })) as Array<{ name: string }>;
  return runs[0]?.name ?? null;
}

const defaultDeps: RecoverDeps = {
  sleep: (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
  now: () => Date.now(),
  getStatus: (runId) => getAgentRunStatus(runId),
  findRun: findLatestRun,
  findByKey: findRunByClientKey,
  pollMs: 3000,
  findTimeoutMs: 30_000,
  totalTimeoutMs: 120_000,
};

function abortError(): Error {
  return new DOMException('Aborted', 'AbortError');
}

/**
 * After a gateway timeout the request may still have created (and be running)
 * an Agent Run. Poll it for a bounded time and report its real outcome. Never
 * re-sends the message. If the run is still open at the deadline, resolves
 * with `queued: true` so the regular run-status polling continues from there.
 */
export async function recoverRunAfterGateway(
  params: RecoverParams,
  overrides: Partial<RecoverDeps> = {}
): Promise<RecoveredRun> {
  const deps = { ...defaultDeps, ...overrides };
  const deadline = Math.min(deps.now() + deps.totalTimeoutMs, params.startedAt + MAX_FROM_SEND_MS);
  const check = () => {
    if (params.signal?.aborted) throw abortError();
  };

  let runId = params.runId ?? null;
  if (!runId) {
    const { clientKey, conversationId, startedAt } = params;
    const lookUp = clientKey
      ? () => deps.findByKey(clientKey)
      : conversationId
        ? () => deps.findRun(conversationId, startedAt)
        : null;
    if (!lookUp) {
      throw new Error('The server timed out before confirming the run. Check the conversation list for the result.');
    }
    const findDeadline = deps.now() + deps.findTimeoutMs;
    while (!runId) {
      check();
      try {
        runId = await lookUp();
      } catch {
        runId = null;
      }
      if (runId) break;
      if (deps.now() >= findDeadline) {
        throw new Error('The server timed out and no run was found for this message. It was not sent again.');
      }
      await deps.sleep(deps.pollMs);
    }
  }

  let last: AgentRunStatusResponse | null = null;
  while (true) {
    check();
    try {
      last = await deps.getStatus(runId);
    } catch {
      // A failed poll must not end recovery; the deadline bounds the loop.
    }
    if (last?.status === 'Success' || last?.status === 'Failed') {
      const ok = last.status === 'Success';
      return {
        success: ok,
        queued: false,
        status: last.status,
        response: ok ? last.response ?? '' : undefined,
        error: ok ? undefined : last.error || 'The agent run failed.',
        conversation_id: last.conversation_id ?? params.conversationId,
        agent_run_id: runId,
        agent_message_id: last.agent_message_id ?? undefined,
      };
    }
    if (deps.now() >= deadline) {
      return {
        success: true,
        queued: true,
        status: last?.status ?? 'Queued',
        conversation_id: last?.conversation_id ?? params.conversationId,
        agent_run_id: runId,
      };
    }
    await deps.sleep(deps.pollMs);
  }
}
