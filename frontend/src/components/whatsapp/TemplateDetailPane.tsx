import { useCallback, useEffect, useMemo, useState } from 'react';
import { Loader2, Pencil, Send, Trash2 } from 'lucide-react';
import { format } from 'date-fns';
import { Button } from '@/components/ui/button';
import { errorText, getTemplate, isBridgeUnavailable, type TemplateDetail, type WhatsAppTemplate } from '@/services/whatsappApi';
import { LoadError } from './BridgeUnavailable';
import { TemplatePreview } from './TemplatePreview';
import { CategoryChangeBadge, QualityBadge, SharedPill, StatusBadge, UsedByChips } from './TemplateBadges';
import { SharedTemplateDialog, type SharedAction } from './SharedTemplateDialog';
import { ManagerLink } from './ManagerLink';
import { fromTemplateDetail } from './template/payload';
import { ttlLabel } from './TemplateWizard/draftActions';
import { draftToPreviewModel } from './TemplateWizard/previewModel';
import { localeLabel } from './template/locales';
import { TimeStamp } from './TimeStamp';
import { isSharedTemplate, parseServerTime, rejectionCopy, statusInfo } from './templateModel';

interface Props {
  row: WhatsAppTemplate;
  /** Bumped by the parent when the status changes elsewhere. */
  refreshKey: number;
  onSend: (row: WhatsAppTemplate) => void;
  /** `acknowledgeShared` is true once the user accepted the shared-template warning. */
  onEdit: (detail: TemplateDetail, acknowledgeShared?: boolean) => void;
  /** `acknowledgeShared` is true once the user accepted the shared-template warning. */
  onDelete: (row: WhatsAppTemplate, acknowledgeShared?: boolean) => void;
  /** Open the create flow for a new version (`name_v2`) instead of changing the shared one. */
  onCopy?: (detail: TemplateDetail, suggestedName: string) => void;
  onUnavailable: () => void;
}

function categoryLabel(c?: string) {
  return c === 'MARKETING' ? 'Marketing' : c === 'UTILITY' ? 'Order and account updates' : c === 'AUTHENTICATION' ? 'Authentication' : c || '-';
}

const HEADER_LABEL: Record<string, string> = {
  TEXT: 'Text', IMAGE: 'Image', VIDEO: 'Video', DOCUMENT: 'Document', LOCATION: 'Location',
};

function headerLabel(detail: TemplateDetail): string {
  const format = (detail.header_format || detail.components.header?.type || '').toUpperCase();
  return format ? (HEADER_LABEL[format] ?? format) : 'None';
}

export function TemplateDetailPane({ row, refreshKey, onSend, onEdit, onDelete, onCopy, onUnavailable }: Props) {
  const [sharedAction, setSharedAction] = useState<SharedAction | null>(null);
  const [detail, setDetail] = useState<TemplateDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const wizardDraft = useMemo(() => (detail ? fromTemplateDetail(detail) : null), [detail]);
  const previewModel = useMemo(() => (wizardDraft ? draftToPreviewModel(wizardDraft) : null), [wizardDraft]);

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
  if (!detail || !wizardDraft || !previewModel) return null;

  const info = statusInfo(detail.status);
  const reason = rejectionCopy(detail.state.rejected_reason);
  const updated = detail.state.last_meta_update || detail.state.last_event_at;
  const updatedDate = parseServerTime(updated);
  const showReason = !!reason && ['REJECTED', 'PAUSED', 'DISABLED'].includes(detail.status);
  const sampleRows = Object.entries(wizardDraft.samples)
    .filter(([, value]) => value)
    .map(([key, value]) => ({ key, value, label: key.startsWith('header.') ? `Header {{${key.slice(7)}}}` : `{{${key}}}` }));
  const nextEdit = parseServerTime(detail.next_edit_at);
  const usedBy = row.used_by ?? [];
  const shared = isSharedTemplate(row);
  const startEdit = () => {
    if (shared) setSharedAction('edit');
    else onEdit(detail);
  };
  const startDelete = () => {
    if (shared) setSharedAction('delete');
    else onDelete(row);
  };
  const confirmShared = () => {
    const action = sharedAction;
    setSharedAction(null);
    if (action === 'edit') {
      onEdit(detail, true);
    } else if (action === 'delete') onDelete(row, true);
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1.5">
          <h2 className="font-mono text-base font-semibold text-ink">{detail.template_name}</h2>
          <div className="flex flex-wrap items-center gap-1.5">
            <StatusBadge status={detail.status} />
            <QualityBadge score={detail.state.quality_score} />
            <CategoryChangeBadge pending={detail.category_change_pending} to={detail.correct_category} />
            <SharedPill shared={shared} />
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
                Last updated <TimeStamp value={updated} />
              </p>
            )}
            {detail.previous_category && detail.previous_category !== detail.category && (
              <p role="note" className="text-steel">
                Meta changed this template&apos;s category from {categoryLabel(detail.previous_category)} to {categoryLabel(detail.category)}.
                Edits keep the category Meta assigned unless you change it.
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

          {usedBy.length > 0 && (
            <section className="space-y-1.5 text-xs" aria-label="Used by">
              <UsedByChips users={usedBy} />
              {shared && <p className="text-steel">Meta keeps one copy of this template for the whole account.</p>}
            </section>
          )}

          <dl className="grid grid-cols-[110px_1fr] gap-y-1.5 text-xs">
            <dt className="text-steel">Category</dt><dd className="text-ink">{categoryLabel(detail.category)}</dd>
            <dt className="text-steel">Language</dt><dd className="text-ink">{localeLabel(detail.language_code)}</dd>
            <dt className="text-steel">Variables</dt>
            <dd className="text-ink">{wizardDraft.variableType === 'name' ? 'Named, like {{first_name}}' : 'Numbered, like {{1}}'}</dd>
            <dt className="text-steel">Header</dt><dd className="text-ink">{headerLabel(detail)}</dd>
            {detail.category?.toUpperCase() === 'UTILITY' && (
              <>
                <dt className="text-steel">Valid for</dt>
                <dd className="text-ink">{typeof detail.ttl_seconds === 'number' ? ttlLabel(detail.ttl_seconds) : 'WhatsApp default'}</dd>
              </>
            )}
            {sampleRows.length > 0 && (
              <>
                <dt className="text-steel">Samples</dt>
                <dd>
                  <ul className="space-y-0.5 text-ink">
                    {sampleRows.map(({ key, label, value }) => (
                      <li key={key}><span className="font-mono text-steel">{label}</span> {value}</li>
                    ))}
                  </ul>
                </dd>
              </>
            )}
          </dl>

          <div className="space-y-2 border-t border-line pt-4">
            <div className="flex flex-wrap gap-2">
              <Button size="sm" onClick={() => onSend(row)} disabled={detail.status !== 'APPROVED'}>
                <Send className="mr-1.5 h-4 w-4" /> Send
              </Button>
              <Button size="sm" variant="outline" onClick={startEdit} disabled={!detail.editable}>
                <Pencil className="mr-1.5 h-4 w-4" /> Edit and resubmit
              </Button>
              <Button size="sm" variant="outline" onClick={startDelete}>
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
                {detail.edit_blocked_until && !nextEdit ? ` Try again after ${format(new Date(detail.edit_blocked_until), 'd MMM, HH:mm')}.` : ''}
              </p>
            )}
            {detail.status === 'APPROVED' && typeof detail.edits_left === 'number' && (
              <p className="text-[11px] text-steel">
                {detail.edits_left} {detail.edits_left === 1 ? 'edit' : 'edits'} left in the next 30 days. Approved templates can be edited once a day, up to 10 times in 30 days.
              </p>
            )}
          </div>
        </div>
        <TemplatePreview model={previewModel} />
      </div>
      <SharedTemplateDialog
        open={sharedAction !== null}
        action={sharedAction ?? 'edit'}
        usedBy={usedBy}
        onConfirm={confirmShared}
        onCopy={() => { setSharedAction(null); onCopy?.(detail, `${detail.template_name}_v2`); }}
        onCancel={() => setSharedAction(null)}
      />
    </div>
  );
}
