import { apiCall, isApiError } from '@/lib/api';
import type { WhatsAppResult } from '@/services/whatsappApi';

// Matches huf/ai/whatsapp/broadcast/audiences/api.py. Reads are GET, writes are POST.
const MODULE = 'huf.ai.whatsapp.broadcast.audiences.api';
const READ_METHODS = new Set(['list_audiences', 'get_audience', 'list_members', 'preview_audience_selection', 'get_import_status']);

async function audienceCall<T>(method: string, args: Record<string, unknown>): Promise<WhatsAppResult<T>> {
  const read = READ_METHODS.has(method);
  try {
    const out = await apiCall<Record<string, unknown> | null>(`${MODULE}.${method}`, args, { verb: read ? 'GET' : 'POST' });
    if (out && typeof out === 'object' && out.success === false) return out as unknown as WhatsAppResult<T>;
    return { ...(out && typeof out === 'object' ? out : {}), success: true } as WhatsAppResult<T>;
  } catch (e) {
    return { success: false, error: isApiError(e) ? e.code : 'request_failed', message: e instanceof Error ? e.message : 'Request failed.' };
  }
}

/** Stored values of the Audience "consent_basis" select (the server validates against these exact strings). */
export type ConsentBasis = 'opt-in form' | 'checkout' | 'in-store' | 'inbound message' | 'import with attestation';
export type ConsentPurpose = 'marketing' | 'utility' | 'events';

export const CONSENT_BASES: { value: ConsentBasis; label: string }[] = [
  { value: 'opt-in form', label: 'Opt-in form' },
  { value: 'checkout', label: 'Checkout' },
  { value: 'in-store', label: 'In store' },
  { value: 'inbound message', label: 'Customer messaged first' },
  { value: 'import with attestation', label: 'Imported list (attested)' },
];
export const CONSENT_PURPOSES: { value: ConsentPurpose; label: string }[] = [
  { value: 'marketing', label: 'Marketing' },
  { value: 'utility', label: 'Order and account updates' },
  { value: 'events', label: 'Events' },
];

export interface Audience {
  name: string;
  gateway?: string;
  title: string;
  description?: string | null;
  is_adhoc?: boolean;
  consent_source: string;
  consent_basis: ConsentBasis;
  consent_purposes: ConsentPurpose[];
  default_consent_at?: string | null;
  consent_attested_by?: string | null;
  consent_attested_at?: string | null;
  member_count: number;
  suppressed_count: number;
  creation?: string | null;
  modified?: string | null;
}

export interface AudienceDetail extends Audience {
  tags: { tag: string; count: number }[];
  used_by: { name: string; status: string }[];
  can_see_numbers: boolean;
}

/** create_audience. The server records who confirmed consent and when. */
export interface CreateAudienceInput {
  gateway: string;
  title: string;
  description?: string;
  consent_source: string;
  consent_basis: ConsentBasis;
  consent_purposes: ConsentPurpose[];
  consent_attested: boolean;
  default_consent_at?: string | null;
  is_adhoc?: boolean;
}
/** update_audience: only these can change; basis, attestation and gateway are fixed at creation. */
export interface UpdateAudienceInput {
  title?: string;
  description?: string;
  consent_source?: string;
  consent_purposes?: ConsentPurpose[];
}

export interface AudienceMember {
  /** Full number for Gateway managers, masked (last 4 digits) for read-only users. */
  recipient: string;
  display_name?: string | null;
  tags: string[];
  consent_source?: string | null;
  consent_at?: string | null;
  source?: string | null;
  added_at?: string | null;
  /** "opted_out" | "marketing_opted_out" | null */
  suppressed: string | null;
}

export type OnConflict = 'skip' | 'update' | 'fail';
export interface ImportMapping {
  phone: string;
  name?: string;
  tags?: string;
  consent_source?: string;
  consent_at?: string;
  /** CSV columns that become the template body values, in order. */
  params?: string[];
}
export interface ImportTotals { added: number; updated: number; skipped_total: number; invalid_total: number }
export type ImportResult =
  | ({ queued: false; member_count: number; suppressed_count: number } & ImportTotals)
  | { queued: true; job_id: string; rows: number };
export interface ImportStatus {
  job_id: string;
  audience: string;
  status: 'queued' | 'running' | 'done' | 'failed';
  processed: number;
  total: number;
  result?: ImportTotals;
  error?: string;
}

export interface MemberFilters { search?: string; tags?: string[]; suppressed?: boolean }

export interface AudienceSelectionItem {
  audience: string;
  tags?: string[];
  tag_filter_mode?: 'any' | 'all';
  exclude?: boolean;
}
export interface SelectionCounts {
  total: number;
  dupes: number;
  excluded: number;
  suppressed: number;
  blocked_by_purpose: number;
  final: number;
}
export interface SelectionPreview {
  counts: SelectionCounts;
  per_audience: { audience: string; matched: number; added: number; blocked_by_purpose?: boolean }[];
  blocked: { code: 'audience_purpose_mismatch'; audience: string; message: string }[];
  category?: string | null;
  purpose_required?: string | null;
  /** True when counts were estimated from audience sizes because no broadcast exists yet. */
  estimated?: boolean;
}

export const listAudiences = (gateway: string) =>
  audienceCall<{ audiences: Audience[]; total: number }>('list_audiences', { gateway, limit: 200 });
export const getAudience = (audience: string) => audienceCall<{ audience: AudienceDetail }>('get_audience', { audience });
export const createAudience = (input: CreateAudienceInput) => audienceCall<{ audience: Audience }>('create_audience', { ...input });
export const updateAudience = (audience: string, changes: UpdateAudienceInput) =>
  audienceCall<{ audience: Audience }>('update_audience', { audience, ...changes });
export const deleteAudience = (audience: string) => audienceCall<Record<string, never>>('delete_audience', { audience });
export const importMembers = (a: {
  audience: string; csv_text?: string; rows?: Record<string, string>[]; mapping: ImportMapping; on_conflict: OnConflict;
}) => audienceCall<ImportResult>('import_members', a);
export const getImportStatus = (audience: string, job_id: string) =>
  audienceCall<ImportStatus>('get_import_status', { audience, job_id });
export const removeMembers = (audience: string, recipients: string[]) =>
  audienceCall<{ removed: number; member_count: number; suppressed_count: number }>('remove_members', { audience, recipients });
export const listMembers = (audience: string, filters: MemberFilters, page: number, page_size = 50) =>
  audienceCall<{ members: AudienceMember[]; total: number; masked: boolean }>('list_members', {
    audience,
    search: filters.search,
    tags: filters.tags?.length ? filters.tags : undefined,
    suppressed: filters.suppressed === undefined ? undefined : filters.suppressed ? 1 : 0,
    start: (page - 1) * page_size,
    limit: page_size,
  });
export const previewAudienceSelection = (broadcast: string, selection: AudienceSelectionItem[]) =>
  audienceCall<SelectionPreview>('preview_audience_selection', { broadcast, selection });
