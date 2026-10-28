import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { errorText } from '@/services/whatsappApi';
import { deleteAudience, listAudiences, type Audience } from './audiencesApi';
import { AudienceFormDialog } from './AudienceFormDialog';
import { ImportMembersDialog } from './ImportMembersDialog';
import { MemberTable } from './MemberTable';

type Dialog = { kind: 'form'; audience?: Audience } | { kind: 'import'; audience: Audience } | null;

export function AudiencesPage({ gateway }: { gateway: string }) {
  const [audiences, setAudiences] = useState<Audience[] | null>(null);
  const [error, setError] = useState('');
  const [open, setOpen] = useState<string | null>(null);
  const [dialog, setDialog] = useState<Dialog>(null);
  const [armed, setArmed] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  const load = useCallback(async () => {
    const res = await listAudiences(gateway);
    if (!res.success) { setError(errorText(res)); setAudiences([]); return; }
    setError('');
    setAudiences(res.audiences);
  }, [gateway]);
  useEffect(() => { void load(); }, [load]);

  const remove = async (a: Audience) => {
    const res = await deleteAudience(a.name);
    setArmed(null);
    if (!res.success) { toast.error(errorText(res)); return; }
    toast.success('Audience deleted');
    if (open === a.name) setOpen(null);
    void load();
  };

  const selected = audiences?.find((a) => a.name === open);
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold">Audiences</h3>
          <p className="text-xs text-steel">Reusable lists of contacts who agreed to hear from you.</p>
        </div>
        <Button onClick={() => setDialog({ kind: 'form' })}>New audience</Button>
      </div>
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      {audiences && audiences.length === 0 && !error && (
        <p className="text-sm text-steel">No audiences yet. Create one, then import your contacts.</p>
      )}
      <ul className="space-y-2">
        {(audiences ?? []).map((a) => (
          <li key={a.name} className="rounded-md border p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <p className="text-sm font-medium">{a.title}</p>
                <p className="text-xs text-steel">
                  {`${a.member_count} contacts${a.suppressed_count ? `, ${a.suppressed_count} opted out` : ''} · ${a.consent_source}`}
                </p>
                <div className="mt-1 space-x-1">{a.consent_purposes.map((p) => <Badge key={p} variant="secondary">{p}</Badge>)}</div>
              </div>
              <div className="flex gap-1">
                <Button variant="outline" size="sm" onClick={() => setOpen(open === a.name ? null : a.name)}>
                  {open === a.name ? 'Hide contacts' : 'View contacts'}
                </Button>
                <Button variant="outline" size="sm" onClick={() => setDialog({ kind: 'import', audience: a })}>Import</Button>
                <Button variant="ghost" size="sm" onClick={() => setDialog({ kind: 'form', audience: a })}>Edit</Button>
                {armed === a.name ? (
                  <Button variant="destructive" size="sm" onClick={() => void remove(a)}>Confirm delete</Button>
                ) : (
                  <Button variant="ghost" size="sm" onClick={() => setArmed(a.name)}>Delete</Button>
                )}
              </div>
            </div>
            {selected?.name === a.name && (
              <div className="mt-3 border-t pt-3">
                <MemberTable audience={a.name} refreshKey={tick} onChanged={() => void load()} />
              </div>
            )}
          </li>
        ))}
      </ul>
      {dialog?.kind === 'form' && (
        <AudienceFormDialog
          gateway={gateway}
          audience={dialog.audience}
          onClose={() => setDialog(null)}
          onSaved={() => { setDialog(null); void load(); }}
        />
      )}
      {dialog?.kind === 'import' && (
        <ImportMembersDialog
          audience={dialog.audience.name}
          title={dialog.audience.title}
          onClose={() => setDialog(null)}
          onDone={() => { void load(); setTick((n) => n + 1); }}
        />
      )}
    </div>
  );
}
