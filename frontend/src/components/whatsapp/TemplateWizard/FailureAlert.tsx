import { Alert, AlertDescription } from '@/components/ui/alert';
import type { WhatsAppError } from '@/services/whatsappApi';

/** What Meta (or Huf) said about a failed submit; shown above the wizard steps. */
export interface FailureDetail {
  title?: string;
  message?: string;
  code?: number | null;
  subcode?: number | null;
  traceId?: string;
  quotaKept?: boolean;
}

/** Pull the structured Meta detail out of an error result; undefined when there is none. */
export function failureDetail(res: WhatsAppError): FailureDetail | undefined {
  const title = res.user_title?.trim();
  const message = res.user_msg?.trim();
  const code = res.graph_code ?? null;
  const subcode = res.subcode ?? null;
  const traceId = res.trace_id?.trim();
  const quotaKept = res.quota_used === false;
  if (!title && !message && subcode == null && !traceId && !quotaKept) return undefined;
  return { title, message, code, subcode, traceId, quotaKept };
}

export function FailureAlert({ notices, detail }: { notices: string[]; detail?: FailureDetail }) {
  const reference = [
    detail?.code != null ? `code ${detail.code}` : '',
    detail?.subcode != null ? `subcode ${detail.subcode}` : '',
    detail?.traceId ? `trace ${detail.traceId}` : '',
  ].filter(Boolean);
  return (
    <Alert variant="destructive" role="alert">
      <AlertDescription className="space-y-1">
        {detail?.title && <p className="font-semibold">{detail.title}</p>}
        {detail?.message && <p>{detail.message}</p>}
        {notices.length > 0 && <p>{notices.join(' ')}</p>}
        {detail?.quotaKept && <p className="text-xs">Nothing was changed, and this attempt did not use up an edit.</p>}
        {reference.length > 0 && <p className="text-[11px] opacity-80">Meta reference: {reference.join(' · ')}</p>}
      </AlertDescription>
    </Alert>
  );
}
