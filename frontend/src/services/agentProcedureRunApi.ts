import type { Filter } from 'frappe-js-sdk/lib/db/types';
import { db } from '@/lib/frappe-sdk';
import { doctype } from '@/data/doctypes';
import { handleFrappeError } from '@/lib/frappe-error';

/**
 * One row of `Agent Procedure Step` — per-node execution state on an
 * `Agent Procedure Run`.
 */
export interface AgentProcedureStepRow {
  name: string;
  node_id: string;
  node_type?: string;
  status?: string;
  attempt?: number;
  started_at?: string | null;
  completed_at?: string | null;
  error?: string | null;
}

interface AgentProcedureRunDoc {
  name: string;
  procedure?: string;
  procedure_id?: string;
  status?: string;
  agent_run?: string;
  pinned_fingerprint?: string;
  pinned_definition_json?: {
    procedure_name?: string;
    version?: number;
    [key: string]: unknown;
  } | string | null;
  started_at?: string | null;
  completed_at?: string | null;
  steps?: AgentProcedureStepRow[];
}

interface AgentProcedureDoc {
  name: string;
  procedure_name?: string;
  version?: number;
}

/** Everything the collapsed procedure row (D8) needs, in one shape. */
export interface ProcedureRunSummary {
  id: string;
  /** `Agent Procedure` id this run pinned — the graph viewer's click-through target. */
  procedureId?: string;
  procedureName: string;
  version?: number;
  status?: string;
  stepCount: number;
  durationMs?: number;
  steps: AgentProcedureStepRow[];
}

function parsePinnedDefinition(
  raw: AgentProcedureRunDoc['pinned_definition_json']
): { procedure_name?: string; version?: number } {
  if (!raw) return {};
  if (typeof raw === 'string') {
    try {
      return JSON.parse(raw) as { procedure_name?: string; version?: number };
    } catch {
      return {};
    }
  }
  return raw;
}

function durationMsFromTimestamps(started?: string | null, completed?: string | null): number | undefined {
  if (!started || !completed) return undefined;
  const start = new Date(started).getTime();
  const end = new Date(completed).getTime();
  if (Number.isNaN(start) || Number.isNaN(end) || end < start) return undefined;
  return end - start;
}

/**
 * Fetch an `Agent Procedure Run` with its `Agent Procedure Step` rows and
 * enough of the pinned `Agent Procedure` (name + version) to label the
 * collapsed transcript row per D8. Falls back to the linked `Agent Procedure`
 * doc when the pinned definition snapshot doesn't carry a name/version.
 */
export async function getProcedureRunSummary(procedureRunId: string): Promise<ProcedureRunSummary | undefined> {
  if (!procedureRunId) return undefined;
  try {
    const run = (await db.getDoc(doctype['Agent Procedure Run'], procedureRunId)) as AgentProcedureRunDoc;
    const pinned = parsePinnedDefinition(run.pinned_definition_json);

    let procedureName = pinned.procedure_name;
    let version = pinned.version;

    if ((!procedureName || version === undefined) && run.procedure) {
      try {
        const procedure = (await db.getDoc(doctype['Agent Procedure'], run.procedure)) as AgentProcedureDoc;
        procedureName = procedureName ?? procedure.procedure_name ?? procedure.name;
        version = version ?? procedure.version;
      } catch {
        // Non-critical — fall through with whatever we already have.
      }
    }

    const steps = run.steps ?? [];

    return {
      id: run.name,
      procedureId: run.procedure,
      procedureName: procedureName ?? run.procedure_id ?? run.procedure ?? 'Procedure',
      version,
      status: run.status,
      stepCount: steps.length,
      durationMs: durationMsFromTimestamps(run.started_at, run.completed_at),
      steps,
    };
  } catch (error) {
    handleFrappeError(error, `Error fetching procedure run ${procedureRunId}`);
    return undefined;
  }
}

/**
 * Resolve which `Agent Tool Call` rows (by name) belong to an
 * `Agent Procedure Run`, so the chat transcript can group tool calls that
 * share a non-null `agent_procedure_run` into one collapsed row (D8)
 * instead of rendering them individually.
 *
 * Returns a map of `tool_call_id` (the call_id used elsewhere in the chat
 * UI) -> `agent_procedure_run` id, omitting calls with no procedure run.
 */
export async function getProcedureRunsForToolCalls(toolCallIds: string[]): Promise<Record<string, string>> {
  const ids = Array.from(new Set(toolCallIds.filter(Boolean)));
  if (ids.length === 0) return {};

  try {
    const rows = await db.getDocList(doctype['Agent Tool Call'], {
      fields: ['name', 'call_id', 'agent_procedure_run'],
      filters: [['call_id', 'in', ids]] as Filter<Record<string, unknown>>[],
      limit: ids.length,
    });

    const result: Record<string, string> = {};
    for (const row of rows as { call_id?: string; agent_procedure_run?: string }[]) {
      if (row.call_id && row.agent_procedure_run) {
        result[row.call_id] = row.agent_procedure_run;
      }
    }
    return result;
  } catch (error) {
    handleFrappeError(error, 'Error resolving procedure runs for tool calls');
    return {};
  }
}
