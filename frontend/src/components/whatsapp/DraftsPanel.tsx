import { useMemo, useState } from 'react';
import { toast } from 'sonner';
import { ArrowLeft, Loader2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import {
  approveTemplateDraft, errorText, getTemplate, isBridgeUnavailable, rejectTemplateDraft, type TemplateDraft,
} from '@/services/whatsappApi';
import { TemplatePreview } from './TemplatePreview';
import { fromDraftPayload } from './template/payload';
import { ReviewStep } from './TemplateWizard/ReviewStep';
import { draftToPreviewModel } from './TemplateWizard/previewModel';
import { StatusBadge } from './TemplateBadges';
import { OPEN_DRAFT_STATUSES, draftStatusInfo, timeAgo } from './templateModel';

const TONE = { success: 'pill-success', warning: 'pill-warning', danger: 'pill-danger', neutral: 'pill-neutral' } as const;

interface Props {
  drafts: TemplateDraft[];
  isAdmin: boolean;
  onChanged: () => void;
  onUnavailable: () => void;
}

export function DraftsPanel({ drafts, isAdmin, onChanged, onUnavailable }: Props) {
  const [busy, setBusy] = useState('');
  const [toReject, setToReject] = useState<TemplateDraft | null>(null);
  const [note, setNote] = useState('');
  /** Meta status of drafts approved in this session, keyed by draft name. */
  const [outcome, setOutcome] = useState<Record<string, string>>({});
  /** Draft open in the full review (same summary and preview as the last wizard step). */
  const [reviewing, setReviewing] = useState<string | null>(null);

  const open = drafts.filter((d) => OPEN_DRAFT_STATUSES.includes(d.status));
  const handled = drafts.filter((d) => !OPEN_DRAFT_STATUSES.includes(d.status));

  const approve = async (d: TemplateDraft): Promise<boolean> => {
    setBusy(d.name);
    const res = await approveTemplateDraft(d.name);
    if (res.success) {
      toast.success(`${d.template_name} submitted to WhatsApp`);
      const detail = res.submitted_template ? await getTemplate(res.submitted_template) : null;
      setOutcome((o) => ({ ...o, [d.name]: detail && detail.success ? detail.status : 'PENDING' }));
    } else if (isBridgeUnavailable(res)) onUnavailable();
    else toast.error(res.submit_error || errorText(res));
    setBusy('');
    onChanged();
    return res.success;
  };

  const reject = async () => {
    if (!toReject) return;
    setBusy(toReject.name);
    const res = await rejectTemplateDraft(toReject.name, note.trim());
    setBusy('');
    if (res.success) {
      toast.success('Draft rejected');
      setToReject(null);
      setNote('');
      setReviewing(null);
      onChanged();
    } else toast.error(errorText(res));
  };

  const previewOf = (d: TemplateDraft) => draftToPreviewModel(fromDraftPayload(d));

  const card = (d: TemplateDraft) => {
    const info = draftStatusInfo(d.status);
    const isOpen = OPEN_DRAFT_STATUSES.includes(d.status);
    const by = d.requested_via === 'Agent run' ? 'an agent' : d.requested_by || 'a teammate';
    const submitted = outcome[d.name];
    return (
      <li key={d.name} className="grid gap-4 rounded-sm border border-line p-4 md:grid-cols-[minmax(0,1fr)_300px]">
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-sm text-ink">{d.template_name}</span>
            <Badge variant={TONE[info.tone]}>{info.label}</Badge>
          </div>
          <p className="text-xs text-steel">
            {d.category === 'MARKETING' ? 'Marketing' : 'Utility'} · {d.language_code} · Requested by {by}
            {d.creation ? ` · ${timeAgo(d.creation)}` : ''}
          </p>
          {d.status === 'Failed' && d.submit_error && (
            <p role="alert" className="text-xs text-destructive">WhatsApp did not accept it: {d.submit_error}</p>
          )}
          {d.review_note && <p className="text-xs text-steel">Note: {d.review_note}</p>}
          {submitted && (
            <p className="flex items-center gap-2 text-xs text-steel">Now at WhatsApp: <StatusBadge status={submitted} /></p>
          )}
          <Button size="sm" variant={isOpen && isAdmin ? 'default' : 'outline'} onClick={() => setReviewing(d.name)}>
            {isOpen && isAdmin ? 'Review' : 'View'}
          </Button>
          {isOpen && !isAdmin && <p className="text-xs text-steel">An admin needs to approve this before it goes to WhatsApp.</p>}
        </div>
        <TemplatePreview model={previewOf(d)} />
      </li>
    );
  };

  const rejectDialog = (
    <Dialog open={!!toReject} onOpenChange={(o) => !o && setToReject(null)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Reject draft?</DialogTitle>
          <DialogDescription>
            {toReject?.template_name} will not be sent to WhatsApp. You can leave a note for the person who asked.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-1">
          <Label htmlFor="wa-reject-note">Note (optional)</Label>
          <Textarea id="wa-reject-note" value={note} onChange={(e) => setNote(e.target.value)} />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setToReject(null)}>Cancel</Button>
          <Button onClick={reject} disabled={!!busy}>Reject draft</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );

  const current = drafts.find((d) => d.name === reviewing);
  if (current) {
    const isOpen = OPEN_DRAFT_STATUSES.includes(current.status);
    const by = current.requested_via === 'Agent run' ? 'an agent' : current.requested_by || 'a teammate';
    return (
      <div className="space-y-6">
        <Button variant="ghost" size="sm" onClick={() => setReviewing(null)}>
          <ArrowLeft className="mr-1.5 h-4 w-4" /> Back to drafts
        </Button>
        <DraftReview draft={current} by={by} isOpen={isOpen} isAdmin={isAdmin} busy={busy === current.name}
          submitted={outcome[current.name]}
          onApprove={async () => { if (await approve(current)) setReviewing(null); }}
          onReject={() => { setToReject(current); setNote(''); }} />
        {rejectDialog}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {open.length === 0 ? (
        <p className="rounded-sm border border-line p-6 text-center text-xs text-steel">
          No drafts are waiting. Templates requested by teammates or agents show up here for approval.
        </p>
      ) : (
        <ul className="space-y-3">{open.map(card)}</ul>
      )}
      {handled.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-[11px] uppercase tracking-wide text-steel">Handled</h3>
          <ul className="space-y-3">{handled.map(card)}</ul>
        </div>
      )}

      {rejectDialog}
    </div>
  );
}

interface ReviewProps {
  draft: TemplateDraft;
  by: string;
  isOpen: boolean;
  isAdmin: boolean;
  busy: boolean;
  submitted?: string;
  onApprove: () => void;
  onReject: () => void;
}

/** One draft in the same review layout as the last wizard step, with the admin decision below. */
function DraftReview({ draft, by, isOpen, isAdmin, busy, submitted, onApprove, onReject }: ReviewProps) {
  const wizardDraft = useMemo(() => fromDraftPayload(draft), [draft]);
  const info = draftStatusInfo(draft.status);
  const kindLabel = draft.category === 'UTILITY' ? 'Utility' : 'Marketing';
  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="font-mono text-base font-semibold text-ink">{draft.template_name}</h2>
          <Badge variant={TONE[info.tone]}>{info.label}</Badge>
        </div>
        <p className="text-xs text-steel">
          Requested by {by}{draft.creation ? ` · ${timeAgo(draft.creation)}` : ''}
        </p>
        {draft.status === 'Failed' && draft.submit_error && (
          <p role="alert" className="text-xs text-destructive">WhatsApp did not accept it: {draft.submit_error}</p>
        )}
        {draft.review_note && <p className="text-xs text-steel">Note: {draft.review_note}</p>}
        {submitted && <p className="flex items-center gap-2 text-xs text-steel">Now at WhatsApp: <StatusBadge status={submitted} /></p>}
      </div>
      <ReviewStep
        draft={wizardDraft}
        kindLabel={kindLabel}
        isEdit={false}
        direct={false}
        intro={isOpen && isAdmin ? 'Check the request. Approving sends it to WhatsApp for review.' : 'This is what was requested.'}
      />
      {isOpen && isAdmin && (
        <div className="flex flex-wrap items-center justify-end gap-2 border-t border-line pt-4">
          <Button variant="outline" disabled={busy} onClick={onReject}>Reject</Button>
          <Button disabled={busy} onClick={onApprove}>
            {busy && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" aria-hidden />}
            {draft.status === 'Failed' ? 'Try again' : 'Approve & submit'}
          </Button>
        </div>
      )}
      {isOpen && !isAdmin && <p className="text-xs text-steel">An admin needs to approve this before it goes to WhatsApp.</p>}
    </div>
  );
}
