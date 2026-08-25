import type { Filter } from 'frappe-js-sdk/lib/db/types';
import { call, db } from '@/lib/frappe-sdk';
import { doctype } from '@/data/doctypes';
import { handleFrappeError } from '@/lib/frappe-error';
import type { PaginationParams, PaginatedResponse } from '@/types/pagination';

export type AgentProcedureStatus = 'Draft' | 'Testing' | 'Active' | 'Disabled' | 'Archived';
export type AgentProcedureTier = 'System' | 'Compiled' | 'Draft';

export interface AgentProcedureProvenance {
  source?: string;
  source_flow_id?: string;
  source_flow_fingerprint?: string;
  [key: string]: unknown;
}

export type AgentProcedureApprovalStatus = 'Not Requested' | 'Pending Review' | 'Approved' | 'Rejected';

export interface AgentProcedureDoc {
  name: string;
  procedure_id?: string;
  procedure_name?: string;
  version?: number;
  status?: AgentProcedureStatus;
  tier?: AgentProcedureTier;
  schema_version?: string;
  fingerprint?: string;
  definition_json?: string;
  input_schema?: string;
  output_schema?: string;
  applicability?: string;
  permission_envelope?: string;
  is_read_only?: 0 | 1;
  contains_writes?: 0 | 1;
  contains_code?: 0 | 1;
  provenance?: string;
  created_from_agent?: string;
  created_from_runs?: string;
  confidence?: number;
  is_system?: 0 | 1;
  updated_by?: string;
  updated_at?: string;
  creation?: string;
  modified?: string;
  approval_status?: AgentProcedureApprovalStatus;
  approved_by?: string;
  approved_at?: string;
  approval_note?: string;
}

export interface AgentProcedureListParams extends PaginationParams {
  status?: string;
  tier?: string;
}

const LIST_FIELDS = [
  'name',
  'procedure_id',
  'procedure_name',
  'version',
  'status',
  'tier',
  'is_read_only',
  'provenance',
  'creation',
  'modified',
];

/** Parses the `provenance` JSON string and returns the source Flow id, when this
 * Procedure was created via Flow -> Procedure conversion (see huf.ai.flow_api). */
export function getSourceFlowId(doc: Pick<AgentProcedureDoc, 'provenance'>): string | undefined {
  if (!doc.provenance) return undefined;
  try {
    const parsed = JSON.parse(doc.provenance) as AgentProcedureProvenance;
    return parsed.source === 'flow_conversion' ? parsed.source_flow_id : undefined;
  } catch {
    return undefined;
  }
}

export async function getAgentProcedures(
  params: AgentProcedureListParams = {}
): Promise<PaginatedResponse<AgentProcedureDoc>> {
  const { limit = 20, start = 0, status, tier } = params;

  const filters: Array<[string, string, unknown]> = [];
  if (status && status !== 'all') filters.push(['status', '=', status]);
  if (tier && tier !== 'all') filters.push(['tier', '=', tier]);

  try {
    const procedures = await db.getDocList(doctype['Agent Procedure'], {
      fields: LIST_FIELDS,
      filters: (filters.length ? filters : undefined) as Filter<Record<string, unknown>>[] | undefined,
      orderBy: { field: 'modified', order: 'desc' },
      limit: limit + 1,
      limit_start: start,
    });

    const hasMore = procedures.length > limit;
    return {
      data: (hasMore ? procedures.slice(0, limit) : procedures) as AgentProcedureDoc[],
      hasMore,
    };
  } catch (error) {
    handleFrappeError(error, 'Error fetching Agent Procedures');
    return { data: [], hasMore: false };
  }
}

/** Read-only, eligible-for-binding Procedures — the picker used by binding UIs must
 * only ever offer procedures where `is_read_only` is true (I8/tier-lock constraint). */
export async function getReadOnlyAgentProcedures(): Promise<AgentProcedureDoc[]> {
  try {
    return (await db.getDocList(doctype['Agent Procedure'], {
      fields: LIST_FIELDS,
      filters: [['is_read_only', '=', 1]] as Filter<Record<string, unknown>>[],
      orderBy: { field: 'procedure_name', order: 'asc' },
      limit: 500,
    })) as AgentProcedureDoc[];
  } catch (error) {
    handleFrappeError(error, 'Error fetching read-only Agent Procedures');
    return [];
  }
}

export async function getAgentProcedure(name: string): Promise<AgentProcedureDoc | undefined> {
  try {
    return (await db.getDoc(doctype['Agent Procedure'], name)) as AgentProcedureDoc;
  } catch (error) {
    handleFrappeError(error, `Error fetching Agent Procedure ${name}`);
  }
}

/** Prior versions of a Procedure — same `procedure_id`, ordered newest first. Lets the
 * detail page show version history without a dedicated version-history doctype. */
export async function getAgentProcedureVersionHistory(
  procedureId: string,
  excludeName?: string
): Promise<AgentProcedureDoc[]> {
  if (!procedureId) return [];
  try {
    const filters: Array<[string, string, unknown]> = [['procedure_id', '=', procedureId]];
    const versions = (await db.getDocList(doctype['Agent Procedure'], {
      fields: ['name', 'procedure_id', 'procedure_name', 'version', 'status', 'tier', 'fingerprint', 'modified'],
      filters: filters as Filter<Record<string, unknown>>[],
      orderBy: { field: 'version', order: 'desc' },
      limit: 50,
    })) as AgentProcedureDoc[];
    return excludeName ? versions.filter((v) => v.name !== excludeName) : versions;
  } catch (error) {
    handleFrappeError(error, `Error fetching version history for ${procedureId}`);
    return [];
  }
}

export interface ProcedureValidationRunResult {
  run_name: string;
  status: string;
  passed: boolean;
  error?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
}

export interface ProcedureValidationResult {
  procedure_name: string;
  is_read_only: boolean;
  contains_writes: boolean;
  runs: ProcedureValidationRunResult[];
  promotion: {
    approved: boolean;
    reasons: string[];
  };
  diagnostics: string[];
}

/** Runs the T-50 validation harness (`huf.ai.graph.validation_harness`) against this
 * Procedure's real run history and returns its promotion decision. See
 * `huf.ai.procedure_validation_api.run_validation_harness` for what is and is not measured. */
export async function runProcedureValidation(
  procedureName: string,
  runs?: number
): Promise<ProcedureValidationResult | undefined> {
  try {
    const result = await call.get('huf.ai.procedure_validation_api.run_validation_harness', {
      procedure_name: procedureName,
      ...(runs ? { runs } : {}),
    });
    return (result?.message ?? result) as ProcedureValidationResult;
  } catch (error) {
    handleFrappeError(error, `Error running validation harness for ${procedureName}`);
  }
}

export interface ProcedureApprovalResult {
  procedure_name: string;
  approval_status: AgentProcedureApprovalStatus;
  approved_by?: string;
  approved_at?: string;
  changed: boolean;
}

/** Flags a write Procedure (is_read_only=0) as ready for manual review. Any user with
 * Agent Procedure read access may call this -- it grants no binding rights by itself,
 * see `approveProcedure`. See `huf.ai.procedure_approval_api.request_procedure_approval`. */
export async function requestProcedureApproval(
  procedureName: string
): Promise<ProcedureApprovalResult | undefined> {
  try {
    const result = await call.post('huf.ai.procedure_approval_api.request_procedure_approval', {
      procedure_name: procedureName,
    });
    return (result?.message ?? result) as ProcedureApprovalResult;
  } catch (error) {
    handleFrappeError(error, `Error requesting review for ${procedureName}`);
  }
}

/** Approves or rejects a write Procedure for binding. Restricted server-side to System
 * Manager / Huf Manager (I8 gate) -- see
 * `huf.ai.procedure_approval_api.approve_procedure`. */
export async function approveProcedure(
  procedureName: string,
  approve: boolean,
  note?: string
): Promise<ProcedureApprovalResult | undefined> {
  try {
    const result = await call.post('huf.ai.procedure_approval_api.approve_procedure', {
      procedure_name: procedureName,
      approve,
      ...(note ? { note } : {}),
    });
    return (result?.message ?? result) as ProcedureApprovalResult;
  } catch (error) {
    handleFrappeError(error, `Error recording approval decision for ${procedureName}`);
  }
}
