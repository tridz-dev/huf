import { useState } from 'react';
import { toast } from 'sonner';
import { Loader2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import {
  approveTemplateDraft, errorText, getTemplate, isBridgeUnavailable, rejectTemplateDraft, type TemplateDraft,
} from '@/services/whatsappApi';
import { TemplatePreview } from './TemplatePreview';
import { StatusBadge } from './TemplateBadges';
import { OPEN_DRAFT_STATUSES, draftStatusInfo, payloadToPreviewInput, timeAgo } from './templateModel';

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

  const open = drafts.filter((d) => OPEN_DRAFT_STATUSES.includes(d.status));
  const handled = drafts.filter((d) => !OPEN_DRAFT_STATUSES.includes(d.status));

  const approve = async (d: TemplateDraft) => {
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
      onChanged();
    } else toast.error(errorText(res));
  };

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
          {isOpen && isAdmin && (
            <div className="flex gap-2 pt-1">
              <Button size="sm" disabled={busy === d.name} onClick={() => approve(d)}>
                {busy === d.name && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />}
                {d.status === 'Failed' ? 'Try again' : 'Approve and submit'}
              </Button>
              <Button size="sm" variant="outline" disabled={busy === d.name} onClick={() => { setToReject(d); setNote(''); }}>
                Reject
              </Button>
            </div>
          )}
          {isOpen && !isAdmin && <p className="text-xs text-steel">An admin needs to approve this before it goes to WhatsApp.</p>}
        </div>
        <TemplatePreview input={payloadToPreviewInput(d.payload)} />
      </li>
    );
  };

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
    </div>
  );
}
