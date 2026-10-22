import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Loader2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { LoadError } from '@/components/whatsapp/BridgeUnavailable';
import { TimeStamp } from '@/components/whatsapp/TimeStamp';
import { createBindingCodeForMe, listBindings, revokeBinding, type Binding } from '@/services/telegramMessagesApi';

const SCOPES = ['Viewer', 'Operator', 'Admin'];

/** Telegram accounts bound to Huf users (the admin cockpit). The one-time code is shown once. */
export function BindingsTab({ gateway }: { gateway: string }) {
	const [items, setItems] = useState<Binding[]>([]);
	const [loading, setLoading] = useState(true);
	const [error, setError] = useState('');
	const [busy, setBusy] = useState('');
	const [mintOpen, setMintOpen] = useState(false);
	const [scope, setScope] = useState('Viewer');
	const [minted, setMinted] = useState<{ code: string; instructions: string; expires_in: number } | null>(null);
	const [mintError, setMintError] = useState('');

	const load = useCallback(async () => {
		setLoading(true);
		setError('');
		const res = await listBindings(gateway);
		if (res.ok) setItems(res.data.items);
		else { setItems([]); setError(res.error); }
		setLoading(false);
	}, [gateway]);
	useEffect(() => { void load(); }, [load]);

	const revoke = async (b: Binding) => {
		setBusy(b.name);
		const res = await revokeBinding(gateway, b.name);
		if (res.ok) { toast.success('Binding revoked'); await load(); } else toast.error(res.error);
		setBusy('');
	};
	const mint = async () => {
		setMintError('');
		const res = await createBindingCodeForMe(gateway, scope);
		if (res.ok) setMinted({ code: res.data.code, instructions: res.data.instructions, expires_in: res.data.expires_in });
		else setMintError(res.error);
	};
	const closeMint = () => { setMintOpen(false); setMinted(null); setMintError(''); };

	return (
		<div className="space-y-3">
			<div className="flex items-center justify-between">
				<p className="text-xs text-steel">Telegram accounts linked to Huf users can run the admin cockpit from chat.</p>
				<Button size="sm" onClick={() => setMintOpen(true)}>Bind my Telegram</Button>
			</div>
			{error && <LoadError message={error} onRetry={load} />}
			{loading ? (
				<div className="flex items-center gap-2 text-xs text-steel"><Loader2 className="h-4 w-4 animate-spin" /> Loading...</div>
			) : items.length === 0 && !error ? (
				<p className="rounded-sm border border-line p-6 text-center text-xs text-steel">No Telegram accounts are bound yet.</p>
			) : items.length > 0 ? (
				<div className="rounded-sm border border-line">
					<Table>
						<TableHeader>
							<TableRow><TableHead>Huf user</TableHead><TableHead>Telegram</TableHead><TableHead>Role</TableHead><TableHead>Status</TableHead><TableHead>Last seen</TableHead><TableHead className="text-right">Actions</TableHead></TableRow>
						</TableHeader>
						<TableBody>
							{items.map((b) => (
								<TableRow key={b.name}>
									<TableCell className="text-xs">{b.frappe_user}</TableCell>
									<TableCell className="text-xs"><span className="font-mono">{b.telegram_user_id}</span>{b.telegram_username && <span className="text-steel"> @{b.telegram_username}</span>}</TableCell>
									<TableCell className="text-xs">{b.role_scope}</TableCell>
									<TableCell><Badge variant={b.is_active ? 'pill-success' : 'pill-danger'}>{b.is_active ? 'Active' : 'Revoked'}</Badge></TableCell>
									<TableCell className="text-xs text-steel"><TimeStamp value={b.last_seen_at} /></TableCell>
									<TableCell className="text-right">
										{b.is_active && <Button size="sm" variant="outline" disabled={busy === b.name} onClick={() => void revoke(b)}>Revoke</Button>}
									</TableCell>
								</TableRow>
							))}
						</TableBody>
					</Table>
				</div>
			) : null}
			<Dialog open={mintOpen} onOpenChange={(o) => !o && closeMint()}>
				<DialogContent>
					<DialogHeader>
						<DialogTitle>Bind my Telegram</DialogTitle>
						<DialogDescription>Create a one-time code, then send it to the bot in a private chat.</DialogDescription>
					</DialogHeader>
					{minted ? (
						<div className="space-y-2 text-xs">
							<p className="text-steel">This code is shown once. It expires in {Math.round(minted.expires_in / 60)} minutes.</p>
							<code className="block rounded-sm border border-line p-2 font-mono text-sm">{minted.code}</code>
							<p className="text-steel">{minted.instructions}</p>
						</div>
					) : (
						<div className="space-y-2">
							<Select value={scope} onValueChange={setScope}>
								<SelectTrigger aria-label="Role"><SelectValue /></SelectTrigger>
								<SelectContent>{SCOPES.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
							</Select>
							{mintError && <p role="alert" className="text-xs text-destructive">{mintError}</p>}
						</div>
					)}
					<DialogFooter>
						{minted ? <Button onClick={closeMint}>Done</Button> : <Button onClick={() => void mint()}>Create code</Button>}
					</DialogFooter>
				</DialogContent>
			</Dialog>
		</div>
	);
}
