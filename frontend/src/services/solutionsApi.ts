import { call } from '@/lib/frappe-sdk';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import type {
  CreateSolutionPayload,
  EntryPoint,
  Intent,
  NumberSummary,
  Pin,
  RouteDecision,
  SaveEntryPointPayload,
  SimulateRequest,
  SolutionConversation,
  SolutionError,
  SolutionOverview,
  SolutionSummary,
  UpdateSolutionFields,
} from '@/types/solutions';

const READ = 'huf.ai.solutions.read_models';
const WRITE = 'huf.ai.solutions.crud';

/** Thrown by every client function; `code` is a contract error code or `request_failed`. */
export class SolutionsApiError extends Error {
  code: string;
  details?: unknown;
  constructor(code: string, message: string, details?: unknown) {
    super(message);
    this.name = 'SolutionsApiError';
    this.code = code;
    this.details = details;
  }
}

/** Unwrap the `{message: ...}` envelope and convert `{error:{code,message}}` into a thrown error. */
export function unwrapSolutionsResult<T>(res: unknown): T {
  const body = res && typeof res === 'object' && 'message' in res ? (res as { message: unknown }).message : res;
  if (body && typeof body === 'object' && 'error' in body) {
    const err = (body as { error?: SolutionError }).error;
    if (err && typeof err === 'object') {
      throw new SolutionsApiError(err.code || 'unknown_error', err.message || 'Request failed.', body);
    }
  }
  if (body === undefined || body === null) {
    throw new SolutionsApiError('invalid_response', 'Unexpected response from server.');
  }
  return body as T;
}

async function invoke<T>(
  module: string,
  method: string,
  args: Record<string, unknown>,
  verb: 'get' | 'post',
): Promise<T> {
  let res: unknown;
  try {
    const path = `${module}.${method}`;
    res = verb === 'post' ? await call.post(path, args) : await call.get(path, args);
  } catch (err) {
    throw new SolutionsApiError('request_failed', getFrappeErrorMessage(err));
  }
  return unwrapSolutionsResult<T>(res);
}

const read = <T>(method: string, args: Record<string, unknown> = {}) => invoke<T>(READ, method, args, 'get');
const write = <T>(method: string, args: Record<string, unknown> = {}) => invoke<T>(WRITE, method, args, 'post');

// Reads (huf.ai.solutions.read_models)
export const listSolutions = (purpose?: string) =>
  read<SolutionSummary[]>('list_solutions', purpose ? { purpose } : {});
export const getSolutionOverview = (name: string) => read<SolutionOverview>('get_solution_overview', { name });
export const listEntryPoints = (solution: string) => read<EntryPoint[]>('list_entry_points', { solution });
export const getNumberSummary = (gateway: string) => read<NumberSummary>('get_number_summary', { gateway });
export const listSolutionConversations = (solution?: string | null) =>
  read<SolutionConversation[]>('list_solution_conversations', solution ? { solution } : {});
export const getIntents = () => read<Intent[]>('get_intents');
export const simulateRoute = (request: SimulateRequest) =>
  read<RouteDecision>('simulate_route', { request: JSON.stringify(request) });

// Writes (huf.ai.solutions.crud)
export const createSolution = (payload: CreateSolutionPayload) =>
  write<SolutionSummary>('create_solution', { payload: JSON.stringify(payload) });
export const updateSolution = (name: string, fields: UpdateSolutionFields) =>
  write<SolutionSummary>('update_solution', { name, fields: JSON.stringify(fields) });
export const pauseSolution = (name: string) => write<SolutionSummary>('pause_solution', { name });
export const resumeSolution = (name: string) => write<SolutionSummary>('resume_solution', { name });
export const saveEntryPoint = (solution: string, entry: SaveEntryPointPayload) =>
  write<EntryPoint>('save_entry_point', { solution, entry: JSON.stringify(entry) });
export const deleteEntryPoint = (name: string) => write<{ success?: boolean }>('delete_entry_point', { name });
export const goLive = (name: string) => write<SolutionSummary>('go_live', { name });
export const reassignConversation = (gateway: string, contact: string, solution: string, noteMessages?: number) =>
  write<{ pin: Pin }>('reassign_conversation', {
    gateway,
    contact,
    solution,
    ...(noteMessages !== undefined ? { note_messages: noteMessages } : {}),
  });
