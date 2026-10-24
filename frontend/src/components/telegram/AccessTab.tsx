import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Loader2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { LoadError } from '@/components/whatsapp/BridgeUnavailable';
import { TimeStamp } from '@/components/whatsapp/TimeStamp';
import { approveAccess, listAccess, revokeAccess, type AccessEntry } from '@/services/telegramMessagesApi';

const STATES = ['Pending', 'Approved', 'Revoked'] as const;
type State = (typeof STATES)[number];
const LABEL: Record<State, string> = { Pending: 'Waiting', Approved: 'Approved', Revoked: 'Revoked' };
const EMPTY: Record<State, string> = {
	Pending: 'No one is waiting for approval.', Approved: 'No approved people yet.', Revoked: 'No revoked people.',
};

/** Who may talk to the bot: approve pairing requests or revoke access. */
export function AccessTab({ gateway }: { gateway: string }) {
	const [state, setState] = useState<State>('Pending');
	const [entries, setEntries] = useState<AccessEntry[]>([]);
	const [loading, setLoading] = useState(true);
	const [error, setError] = useState('');
	const [busy, setBusy] = useState('');

	const load = useCallback(async () => {
		setLoading(true);
		setError('');
		const res = await listAccess(gateway, state);
		if (res.ok) setEntries(res.data.items);
		else { setEntries([]); setError(res.error); }
		setLoading(false);
	}, [gateway, state]);
	useEffect(() => { void load(); }, [load]);

	const act = async (entry: AccessEntry, action: 'approve' | 'revoke') => {
		setBusy(entry.name);
		const res = action === 'approve' ? await approveAccess(gateway, entry.name) : await revokeAccess(gateway, entry.name);
		if (res.ok) { toast.success(action === 'approve' ? 'Access approved' : 'Access revoked'); await load(); }
		else toast.error(res.error);
		setBusy('');
	};

	return (
		<div className="space-y-3">
			<p className="text-xs text-steel">People who message the bot must be approved before the agent replies, when pairing is on.</p>
			<Tabs value={state} onValueChange={(v) => setState(v as State)}>
				<TabsList>{STATES.map((s) => <TabsTrigger key={s} value={s}>{LABEL[s]}</TabsTrigger>)}</TabsList>
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
							<TableRow><TableHead>Contact</TableHead><TableHead>Code</TableHead><TableHead>Status</TableHead><TableHead>Requested</TableHead><TableHead className="text-right">Actions</TableHead></TableRow>
						</TableHeader>
						<TableBody>
							{entries.map((e) => (
								<TableRow key={e.name}>
									<TableCell className="text-xs">
										<div className="font-mono text-ink">{e.external_id}</div>
										{e.display_label && <div className="text-steel">{e.display_label}</div>}
									</TableCell>
									<TableCell className="font-mono text-xs">{e.pairing_code || ''}</TableCell>
									<TableCell>
										<Badge variant={e.state === 'Approved' ? 'pill-success' : e.state === 'Revoked' ? 'pill-danger' : 'pill-warning'}>{LABEL[e.state as State] ?? e.state}</Badge>
										{e.approved_by && <div className="text-[11px] text-steel">by {e.approved_by}</div>}
									</TableCell>
									<TableCell className="whitespace-nowrap text-xs text-steel"><TimeStamp value={e.creation} /></TableCell>
									<TableCell className="space-x-2 whitespace-nowrap text-right">
										{e.state === 'Pending' && <Button size="sm" disabled={busy === e.name} onClick={() => void act(e, 'approve')}>Approve</Button>}
										{e.state !== 'Revoked' && (
											<Button size="sm" variant="outline" disabled={busy === e.name} onClick={() => void act(e, 'revoke')}>
												{e.state === 'Pending' ? 'Decline' : 'Revoke'}
											</Button>
										)}
									</TableCell>
								</TableRow>
							))}
						</TableBody>
					</Table>
				</div>
			) : null}
		</div>
	);
}
