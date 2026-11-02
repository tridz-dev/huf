import { useCallback, useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { LoadError } from '@/components/whatsapp/BridgeUnavailable';
import { GroupCard } from './GroupCard';
import { JoinQueue } from './JoinQueue';
import {
	guardSummary, listGroups, listJoinRequests, type GuardStatus, type JoinRequest, type KnownGroup,
} from '@/services/telegramGroupsApi';

/** Groups the bot is in, and the people waiting to join them. */
export function GroupsTab({ gateway }: { gateway: string }) {
	const [joins, setJoins] = useState<JoinRequest[]>([]);
	const [groups, setGroups] = useState<KnownGroup[]>([]);
	const [guard, setGuard] = useState<GuardStatus | null>(null);
	const [note, setNote] = useState('');
	const [loading, setLoading] = useState(true);
	const [error, setError] = useState('');

	const load = useCallback(async () => {
		setLoading(true);
		setError('');
		const [j, g] = await Promise.all([listJoinRequests(gateway, 'Pending'), listGroups(gateway)]);
		if (j.ok) { setJoins(j.data.items); setGuard(j.data.guard); } else { setJoins([]); setError(j.error); }
		if (g.ok) { setGroups(g.data.items); setNote(g.data.note ?? ''); setGuard((p) => p ?? g.data.guard); }
		else { setGroups([]); setError((e) => e || g.error); }
		setLoading(false);
	}, [gateway]);
	useEffect(() => { void load(); }, [load]);

	return (
		<div className="space-y-4">
			<p className="text-xs text-steel" data-testid="guard-status">{guardSummary(guard)}</p>
			{error && <LoadError message={error} onRetry={load} />}
			{loading ? (
				<div className="flex items-center gap-2 text-xs text-steel"><Loader2 className="h-4 w-4 animate-spin" /> Loading...</div>
			) : (
				<>
					<section className="space-y-2">
						<h3 className="text-sm font-medium text-ink">Waiting to join</h3>
						<JoinQueue gateway={gateway} items={joins} onChanged={load} />
					</section>
					<section className="space-y-2">
						<h3 className="text-sm font-medium text-ink">Groups</h3>
						{groups.length === 0 ? (
							<p className="rounded-sm border border-line p-6 text-center text-xs text-steel">
								{note || 'The bot is not in any group yet. Add it to a group and it will appear here.'}
							</p>
						) : (
							<div className="grid gap-2 md:grid-cols-2">
								{groups.map((g) => <GroupCard key={g.chat_id} gateway={gateway} group={g} onChanged={load} />)}
							</div>
						)}
					</section>
				</>
			)}
		</div>
	);
}
