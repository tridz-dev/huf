import { TimeStamp } from './TimeStamp';
import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Loader2, UserPlus } from 'lucide-react';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Field } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import {
  addGatewayAccessEntry, approveGatewayPairing, blockGatewayAccessEntry, listGatewayAccessEntries,
  restoreGatewayAccessEntry, revokeGatewayAccessEntry, unblockGatewayAccessEntry,
  type GatewayAccessEntry, type GatewayAccessEntryState,
} from '@/services/gatewayAccessApi';
import { LoadError } from './BridgeUnavailable';

const STATES: GatewayAccessEntryState[] = ['Pending', 'Approved', 'Revoked', 'Blocked', 'Opted out'];
const STATE_LABEL: Record<GatewayAccessEntryState, string> = {
  Pending: 'Waiting',
  Approved: 'Approved',
  Revoked: 'Removed',
  Blocked: 'Blocked',
  'Opted out': 'Opted out',
};
const STATE_BADGE: Record<GatewayAccessEntryState, 'pill-success' | 'pill-danger' | 'pill-warning' | 'pill-neutral'> = {
  Pending: 'pill-warning',
  Approved: 'pill-success',
  Revoked: 'pill-neutral',
  Blocked: 'pill-danger',
  'Opted out': 'pill-neutral',
};
const EMPTY: Record<GatewayAccessEntryState, string> = {
  Pending: 'No one is waiting for approval.',
  Approved: 'No approved senders yet.',
  Revoked: 'No one has been removed or declined.',
  Blocked: 'No one is blocked.',
  'Opted out': 'No one has opted out.',
};
const HELP: Record<GatewayAccessEntryState, string> = {
  Pending: 'People who messaged and are waiting for you. Check the code they tell you against the one shown here.',
  Approved: 'People your agent replies to.',
  Revoked: 'People whose access you removed or whose request you declined. They can ask again after a day, or you can restore them now.',
  Blocked: 'People who are ignored for good. They never get a pairing code.',
  'Opted out': 'People who sent STOP. Only they can opt back in, by sending START.',
};

type Action = 'approve' | 'decline' | 'remove' | 'block' | 'unblock' | 'restore';

/** Asked before an action that cuts someone off; the text says what happens next. */
const CONFIRM: Partial<Record<Action, { title: string; body: string; label: string }>> = {
  remove: {
    title: 'Remove access?',
    body: 'Your agent stops replying to them now. They can ask for access again after a day, or you can restore them from Removed.',
    label: 'Remove access',
  },
  block: {
    title: 'Block this person?',
    body: "Their messages are ignored for good and they never get a pairing code. They aren't told. You can unblock them later.",
    label: 'Block',
  },
};

const DONE: Record<Action, string> = {
  approve: 'Access approved',
  decline: 'Request declined',
  remove: 'Access removed',
  block: 'Blocked',
  unblock: 'Unblocked. They can ask for access again.',
  restore: 'Access restored',
};

function actionsFor(state: GatewayAccessEntryState): Action[] {
  switch (state) {
    case 'Pending':
      return ['approve', 'decline', 'block'];
    case 'Approved':
      return ['remove', 'block'];
    case 'Revoked':
      return ['restore', 'block'];
    case 'Blocked':
      return ['unblock'];
    default:
      return [];
  }
}

const ACTION_LABEL: Record<Action, string> = {
  approve: 'Approve',
  decline: 'Decline',
  remove: 'Remove access',
  block: 'Block',
  unblock: 'Unblock',
  restore: 'Restore access',
};

function AddNumberDialog({ gateway, open, onOpenChange, onAdded }: {
  gateway: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onAdded: () => void;
}) {
  const [phone, setPhone] = useState('');
  const [name, setName] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) {
      setPhone('');
      setName('');
    }
  }, [open]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!phone.trim()) return;
    setSaving(true);
    try {
      await addGatewayAccessEntry({ gateway, externalId: phone.trim(), displayLabel: name.trim() || undefined });
      toast.success('Number added. Your agent will reply to it.');
      onAdded();
      onOpenChange(false);
    } catch (err) {
      toast.error(getFrappeErrorMessage(err));
    }
    setSaving(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={submit} className="space-y-4">
          <DialogHeader>
            <DialogTitle>Add a number</DialogTitle>
            <DialogDescription>They can talk to your agent right away. No message is sent to them.</DialogDescription>
          </DialogHeader>
          <Field label="Phone number" hint="With country code, e.g. 919876543210.">
            <Input value={phone} onChange={(e) => setPhone(e.target.value)} autoFocus />
          </Field>
          <Field label="Name (optional)">
            <Input value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>
              Cancel
            </Button>
            <Button type="submit" disabled={saving || !phone.trim()}>
              {saving && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />}
              Add number
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/** Who may talk to this gateway's agent: approve, decline, remove, block, restore or add people. */
export function AccessTab({ gateway }: { gateway: string }) {
  const [state, setState] = useState<GatewayAccessEntryState>('Pending');
  const [entries, setEntries] = useState<GatewayAccessEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState('');
  const [confirming, setConfirming] = useState<{ entry: GatewayAccessEntry; action: Action } | null>(null);
  const [adding, setAdding] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      setEntries(await listGatewayAccessEntries({ gateway, state }));
    } catch (e) {
      setEntries([]);
      setError(getFrappeErrorMessage(e));
    }
    setLoading(false);
  }, [gateway, state]);
  useEffect(() => { void load(); }, [load]);

  const run = async (entry: GatewayAccessEntry, action: Action) => {
    setBusy(entry.name);
    try {
      let notice = '';
      if (action === 'approve') notice = (await approveGatewayPairing(entry.name)).notification_status;
      else if (action === 'restore') notice = (await restoreGatewayAccessEntry(entry.name)).notification_status;
      else if (action === 'block') await blockGatewayAccessEntry(entry.name);
      else if (action === 'unblock') await unblockGatewayAccessEntry(entry.name);
      else await revokeGatewayAccessEntry(entry.name);
      toast.success(DONE[action]);
      if (/not sent/i.test(notice)) toast.message('The welcome message could not be sent.');
      await load();
    } catch (e) {
      toast.error(getFrappeErrorMessage(e));
    }
    setBusy('');
  };

  const request = (entry: GatewayAccessEntry, action: Action) => {
    if (CONFIRM[action]) setConfirming({ entry, action });
    else void run(entry, action);
  };

  const confirmCopy = confirming ? CONFIRM[confirming.action] : undefined;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <p className="max-w-prose text-xs text-steel">{HELP[state]}</p>
        <Button size="sm" variant="outline" onClick={() => setAdding(true)}>
          <UserPlus className="mr-1.5 h-3.5 w-3.5" /> Add number
        </Button>
      </div>
      <Tabs value={state} onValueChange={(v) => setState(v as GatewayAccessEntryState)}>
        <TabsList>{STATES.map((s) => <TabsTrigger key={s} value={s}>{STATE_LABEL[s]}</TabsTrigger>)}</TabsList>
      </Tabs>
      {error && <LoadError message={error} onRetry={load} />}
      {loading ? (
        <div className="flex items-center gap-2 text-xs text-steel"><Loader2 className="h-4 w-4 animate-spin" /> Loading...</div>
      ) : entries.length === 0 && !error ? (
        <p className="rounded-sm border border-line p-6 text-center text-xs text-steel">{EMPTY[state]}</p>
      ) : entries.length > 0 ? (
        <div className="rounded-sm border border-line">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Contact</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Code</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Requested</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {entries.map((e) => (
                <TableRow key={e.name}>
                  <TableCell className="text-xs">
                    <div className="font-mono text-ink">{e.external_id}</div>
                    {e.display_label && <div className="text-steel">{e.display_label}</div>}
                  </TableCell>
                  <TableCell className="text-xs">{e.entry_type === 'Room' ? 'Group' : 'Person'}</TableCell>
                  <TableCell className="font-mono text-xs">{e.pairing_code || ''}</TableCell>
                  <TableCell>
                    <Badge variant={STATE_BADGE[e.state] ?? 'pill-neutral'}>{STATE_LABEL[e.state] ?? e.state}</Badge>
                    {e.state === 'Approved' && e.approved_by && <div className="text-[11px] text-steel">by {e.approved_by}</div>}
                    {(e.state === 'Revoked' || e.state === 'Blocked') && e.revoked_by && (
                      <div className="text-[11px] text-steel">by {e.revoked_by}</div>
                    )}
                  </TableCell>
                  <TableCell className="whitespace-nowrap text-xs text-steel"><TimeStamp value={e.creation} /></TableCell>
                  <TableCell className="space-x-2 whitespace-nowrap text-right">
                    {actionsFor(e.state).map((action, i) => (
                      <Button
                        key={action}
                        size="sm"
                        variant={i === 0 && (action === 'approve' || action === 'restore') ? 'default' : 'outline'}
                        disabled={busy === e.name}
                        onClick={() => request(e, action)}
                      >
                        {ACTION_LABEL[action]}
                      </Button>
                    ))}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      ) : null}

      <AlertDialog open={Boolean(confirming)} onOpenChange={(open) => !open && setConfirming(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{confirmCopy?.title}</AlertDialogTitle>
            <AlertDialogDescription>{confirmCopy?.body}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => {
                if (confirming) void run(confirming.entry, confirming.action);
                setConfirming(null);
              }}
            >
              {confirmCopy?.label}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AddNumberDialog gateway={gateway} open={adding} onOpenChange={setAdding} onAdded={() => void load()} />
    </div>
  );
}
