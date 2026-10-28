import { apiCall, isApiError } from '@/lib/api';
import type { WhatsAppResult } from '@/services/whatsappApi';

// Backend contract owned by WP-B (audience_api.py). Adjust names here only.
const MODULE = 'huf.ai.whatsapp.broadcast.audience_api';
const READ_METHODS = new Set(['list_audiences', 'get_audience', 'list_members', 'preview_audience_selection']);

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

export type ConsentBasis = 'opt_in_form' | 'checkout' | 'in_store' | 'inbound_message' | 'import_attested';
export type ConsentPurpose = 'marketing' | 'utility' | 'events';

export const CONSENT_BASES: { value: ConsentBasis; label: string }[] = [
  { value: 'opt_in_form', label: 'Opt-in form' },
  { value: 'checkout', label: 'Checkout' },
  { value: 'in_store', label: 'In store' },
  { value: 'inbound_message', label: 'Customer messaged first' },
  { value: 'import_attested', label: 'Imported list (attested)' },
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
  description?: string;
  consent_source: string;
  consent_basis: ConsentBasis;
  consent_purposes: ConsentPurpose[];
  default_consent_at?: string | null;
  consent_attested_by?: string | null;
  consent_attested_at?: string | null;
  member_count: number;
  suppressed_count: number;
  creation?: string;
  modified?: string;
}

export interface AudienceInput {
  gateway?: string;
  title: string;
  description?: string;
  consent_source: string;
  consent_basis: ConsentBasis;
  consent_purposes: ConsentPurpose[];
  default_consent_at?: string | null;
  /** Server records who attested and when; sent only on create. */
  attest?: boolean;
}

export interface AudienceMember {
  name: string;
  recipient: string;
  display_name?: string | null;
  tags: string[];
  params?: Record<string, string>;
  source?: string | null;
  added_at?: string | null;
  suppressed?: boolean;
  suppressed_reason?: string | null;
}

export type OnConflict = 'skip' | 'update' | 'replace_tags';
export interface ImportMapping {
  phone: string;
  name?: string;
  tags?: string;
  /** template variable name -> csv column */
  params?: Record<string, string>;
}
export interface ImportResult {
  added: number;
  updated: number;
  skipped: number;
  invalid: number;
  errors?: { row: number; reason: string }[];
  job?: string;
}

export interface MemberFilters { tags?: string[]; q?: string; suppressed?: boolean }

export interface AudienceSelectionItem {
  audience: string;
  tags?: string[];
  tag_mode?: 'any' | 'all';
  exclude?: boolean;
}
export interface SelectionPreview {
  total: number;
  dupes: number;
  suppressed: number;
  blocked_by_purpose: number;
  final: number;
  per_audience: { audience: string; title?: string; matched: number; suppressed?: number; blocked_by_purpose?: boolean; reason?: string }[];
}

export const listAudiences = (gateway?: string) => audienceCall<{ audiences: Audience[] }>('list_audiences', { gateway });
export const getAudience = (audience: string) => audienceCall<{ audience: Audience; tags?: string[] }>('get_audience', { audience });
export const createAudience = (input: AudienceInput) => audienceCall<{ audience: Audience }>('create_audience', { ...input });
export const updateAudience = (audience: string, changes: Partial<AudienceInput>) =>
  audienceCall<{ audience: Audience }>('update_audience', { audience, ...changes });
export const deleteAudience = (audience: string) => audienceCall<Record<string, never>>('delete_audience', { audience });
export const importMembers = (a: {
  audience: string; csv_text?: string; rows?: Record<string, string>[]; mapping: ImportMapping; on_conflict: OnConflict;
}) => audienceCall<ImportResult>('import_members', a);
export const removeMembers = (audience: string, recipients: string[]) =>
  audienceCall<{ removed: number }>('remove_members', { audience, recipients });
export const listMembers = (audience: string, filters: MemberFilters, page: number, page_size = 50) =>
  audienceCall<{ members: AudienceMember[]; total: number; tags?: string[] }>('list_members', { audience, filters, page, page_size });
export const previewAudienceSelection = (a: { broadcast?: string; selection?: AudienceSelectionItem[]; template?: string }) =>
  audienceCall<SelectionPreview>('preview_audience_selection', a);
