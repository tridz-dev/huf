import { apiCall, isApiError } from '@/lib/api';
import type { WhatsAppResult } from '@/services/whatsappApi';
import type { AudienceSelectionItem, SelectionPreview } from '../../audiences/audiencesApi';

// Matches huf/ai/whatsapp/broadcast/audiences/wiring.py and api.py (preview_audience_selection_for_gateway).
const WIRING = 'huf.ai.whatsapp.broadcast.audiences.wiring';
const API = 'huf.ai.whatsapp.broadcast.audiences.api';

export interface ConsentCover {
  satisfied: boolean;
  attested?: boolean;
  manual_rows: number;
  audiences: { audience: string; title?: string | null; consent_source?: string | null; attested: boolean }[];
}

export interface ExampleRow { row?: number; recipient?: string | null; reason?: string | null }

/** set_broadcast_audiences result: the picked lists are now snapshotted as recipient rows of the Draft. */
export interface BroadcastAudiencesResult extends SelectionPreview {
  added: number;
  skipped: ExampleRow[];
  invalid: ExampleRow[];
  skipped_total?: number;
  invalid_total?: number;
  queued: number;
  consent: ConsentCover;
}

export interface StoredAudiences {
  selection: (AudienceSelectionItem & { title?: string | null })[];
  consent: ConsentCover;
}

async function call<T>(path: string, args: Record<string, unknown>, verb: 'GET' | 'POST'): Promise<WhatsAppResult<T>> {
  try {
    const out = await apiCall<Record<string, unknown> | null>(path, args, { verb });
    if (out && typeof out === 'object' && out.success === false) return out as unknown as WhatsAppResult<T>;
    return { ...(out && typeof out === 'object' ? out : {}), success: true } as WhatsAppResult<T>;
  } catch (e) {
    return { success: false, error: isApiError(e) ? e.code : 'request_failed', message: e instanceof Error ? e.message : 'Request failed.' };
  }
}

export const setBroadcastAudiences = (broadcast: string, selection: AudienceSelectionItem[]) =>
  call<BroadcastAudiencesResult>(`${WIRING}.set_broadcast_audiences`, { broadcast, selection }, 'POST');

export const getBroadcastAudiences = (broadcast: string) =>
  call<StoredAudiences>(`${WIRING}.get_broadcast_audiences`, { broadcast }, 'GET');

/** Live counts before the Draft exists. Pass the template category to apply the purpose rule. */
export const previewAudienceSelectionForGateway = (gateway: string, selection: AudienceSelectionItem[], templateCategory?: string) =>
  call<SelectionPreview>(`${API}.preview_audience_selection_for_gateway`, {
    gateway, selection, ...(templateCategory ? { template_category: templateCategory } : {}),
  }, 'GET');
