import { useEffect, useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { LoadError } from '@/components/whatsapp/BridgeUnavailable';
import { listBusinessConnections, rightLabel, type BusinessConnection } from '@/services/telegramMessagesApi';

/** Read-only view of the Telegram Business accounts connected to this bot. */
export function BusinessConnectionsCard({ gateway }: { gateway: string }) {
	const [items, setItems] = useState<BusinessConnection[] | null>(null);
	const [error, setError] = useState('');
	useEffect(() => {
		let live = true;
		setItems(null);
		void listBusinessConnections(gateway).then((res) => {
			if (!live) return;
			if (res.ok) setItems(res.data.items); else setError(res.error);
		});
		return () => { live = false; };
	}, [gateway]);

	return (
		<Card>
			<CardHeader><CardTitle className="text-sm">Business connections</CardTitle></CardHeader>
			<CardContent className="space-y-3">
				{error ? <LoadError message={error} /> : items === null ? <p className="text-xs text-steel">Loading...</p> : items.length === 0 ? (
					<p className="text-xs text-steel">No business accounts are connected. Connect the bot in Telegram Business settings (Premium).</p>
				) : items.map((c) => (
					<div key={c.id} className="space-y-1 text-xs">
						<div className="flex items-center gap-2">
							<span className="text-ink">{c.owner_name || c.owner_id}</span>
							<Badge variant={c.enabled ? 'pill-success' : 'pill-danger'}>{c.enabled ? 'Connected' : 'Disabled'}</Badge>
						</div>
						<ul className="flex flex-wrap gap-1">
							{Object.entries(c.rights).map(([k, v]) => (
								<li key={k}><Badge variant={v ? 'pill-success' : 'pill-warning'}>{rightLabel(k)}: {v ? 'Yes' : 'No'}</Badge></li>
							))}
						</ul>
					</div>
				))}
			</CardContent>
		</Card>
	);
}
