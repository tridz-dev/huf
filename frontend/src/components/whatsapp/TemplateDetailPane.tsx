import { useCallback, useEffect, useState } from 'react';
import { Loader2, Pencil, Send, Trash2 } from 'lucide-react';
import { format } from 'date-fns';
import { Button } from '@/components/ui/button';
import { errorText, getTemplate, isBridgeUnavailable, type TemplateDetail, type WhatsAppTemplate } from '@/services/whatsappApi';
import { LoadError } from './BridgeUnavailable';
import { TemplatePreview } from './TemplatePreview';
import { CategoryChangeBadge, QualityBadge, StatusBadge } from './TemplateBadges';
import { ManagerLink } from './ManagerLink';
import { detailToPreviewInput, parseServerTime, rejectionCopy, statusInfo, timeAgo } from './templateModel';

interface Props {
  row: WhatsAppTemplate;
  /** Bumped by the parent when the status changes elsewhere. */
  refreshKey: number;
  onSend: (row: WhatsAppTemplate) => void;
  onEdit: (detail: TemplateDetail) => void;
  onDelete: (row: WhatsAppTemplate) => void;
  onUnavailable: () => void;
}

function categoryLabel(c?: string) {
  return c === 'MARKETING' ? 'Marketing' : c === 'UTILITY' ? 'Utility' : c === 'AUTHENTICATION' ? 'Authentication' : c || '-';
}

export function TemplateDetailPane({ row, refreshKey, onSend, onEdit, onDelete, onUnavailable }: Props) {
  const [detail, setDetail] = useState<TemplateDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    const res = await getTemplate(row.name);
    if (res.success) setDetail(res);
    else if (isBridgeUnavailable(res)) onUnavailable();
    else setError(errorText(res));
    setLoading(false);
  }, [row.name, onUnavailable]);

  useEffect(() => {
    setDetail(null);
    void load();
  }, [load, refreshKey]);

  if (error) return <LoadError message={error} onRetry={load} />;
  if (loading && !detail) {
    return <div className="flex items-center gap-2 p-6 text-xs text-steel"><Loader2 className="h-4 w-4 animate-spin" /> Loading template...</div>;
  }
  if (!detail) return null;

  const info = statusInfo(detail.status);
  const reason = rejectionCopy(detail.state.rejected_reason);
  const updated = detail.state.last_meta_update || detail.state.last_event_at;
  const updatedDate = parseServerTime(updated);
  const showReason = !!reason && ['REJECTED', 'PAUSED', 'DISABLED'].includes(detail.status);
  const nextEdit = parseServerTime(detail.next_edit_at);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1.5">
          <h2 className="font-mono text-base font-semibold text-ink">{detail.template_name}</h2>
          <div className="flex flex-wrap items-center gap-1.5">
            <StatusBadge status={detail.status} />
            <QualityBadge score={detail.state.quality_score} />
            <CategoryChangeBadge pending={detail.category_change_pending} to={detail.correct_category} />
          </div>
        </div>
        <ManagerLink url={detail.manager_url} businessId={detail.business_id} showId={false} />
      </div>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="space-y-4">
          <section className="space-y-1 text-xs">
            <p className="text-ink">{info.hint}</p>
            {updatedDate && (
              <p className="text-steel">
                Last updated {timeAgo(updated)} ({format(updatedDate, 'd MMM yyyy, HH:mm')})
              </p>
            )}
            {detail.category_change_pending && (
              <p className="text-steel">
                WhatsApp plans to move this template from {categoryLabel(detail.category).toLowerCase()} to{' '}
                {categoryLabel(detail.correct_category).toLowerCase()}, which can change how it is billed.
              </p>
            )}
          </section>

          {showReason && reason && (
            <section role="note" className="space-y-1 rounded-sm border border-destructive p-3 text-xs">
              <h3 className="font-semibold text-destructive">Why it was not approved</h3>
              <p className="text-ink">{reason.reason}</p>
              <p className="text-steel">{reason.advice}</p>
              {detail.state.rejection_recommendation && (
                <p className="text-steel">WhatsApp suggests: {detail.state.rejection_recommendation}</p>
              )}
            </section>
          )}

          <dl className="grid grid-cols-[110px_1fr] gap-y-1.5 text-xs">
            <dt className="text-steel">Category</dt><dd className="text-ink">{categoryLabel(detail.category)}</dd>
            <dt className="text-steel">Language</dt><dd className="font-mono text-ink">{detail.language_code}</dd>
            {detail.whatsapp_account && (<><dt className="text-steel">Account</dt><dd className="text-ink">{detail.whatsapp_account}</dd></>)}
          </dl>

          <div className="space-y-2 border-t border-line pt-4">
            <div className="flex flex-wrap gap-2">
              <Button size="sm" onClick={() => onSend(row)} disabled={detail.status !== 'APPROVED'}>
                <Send className="mr-1.5 h-4 w-4" /> Send
              </Button>
              <Button size="sm" variant="outline" onClick={() => onEdit(detail)} disabled={!detail.editable}>
                <Pencil className="mr-1.5 h-4 w-4" /> Edit and resubmit
              </Button>
              <Button size="sm" variant="outline" onClick={() => onDelete(row)}>
                <Trash2 className="mr-1.5 h-4 w-4" /> Delete
              </Button>
            </div>
            {detail.status !== 'APPROVED' && (
              <p className="text-[11px] text-steel">Only approved templates can be sent.</p>
            )}
            {!detail.editable && detail.editable_message && (
              <p className="text-[11px] text-steel">
                {detail.editable_message}
                {nextEdit ? ` You can edit again after ${format(nextEdit, 'd MMM, HH:mm')}.` : ''}
              </p>
            )}
            {detail.status === 'APPROVED' && typeof detail.edits_left === 'number' && (
              <p className="text-[11px] text-steel">
                {detail.edits_left} {detail.edits_left === 1 ? 'edit' : 'edits'} left in the next 30 days. Approved templates can be edited once a day, up to 10 times in 30 days.
              </p>
            )}
          </div>
        </div>
        <TemplatePreview input={detailToPreviewInput(detail)} />
      </div>
    </div>
  );
}
