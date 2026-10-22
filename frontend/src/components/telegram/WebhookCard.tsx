import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';

import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { CopyField } from '@/components/ui/copy-field';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { deleteWebhookNow, refreshWebhookHealth, setWebhookNow, type WebhookSummary } from '@/services/telegramCommandsApi';

type Pending = 'set' | 'delete' | null;

function Row({ label, children }: { label: string; children: React.ReactNode }) {
	return (
		<div className="flex items-start justify-between gap-3 text-sm">
			<dt className="text-steel">{label}</dt>
			<dd className="break-all text-right text-ink">{children}</dd>
		</div>
	);
}

/** Where Telegram delivers this bot's messages. Setting or deleting the webhook needs an explicit confirmation. */
export function WebhookCard({ gateway }: { gateway: string }) {
	const [hook, setHook] = useState<WebhookSummary | null>(null);
	const [error, setError] = useState<string | null>(null);
	const [busy, setBusy] = useState(false);
	const [pending, setPending] = useState<Pending>(null);
	const [drop, setDrop] = useState(false);

	const refresh = useCallback(async () => {
		setBusy(true);
		const res = await refreshWebhookHealth(gateway);
		setBusy(false);
		if (res.ok) {
			setHook(res.data.webhook);
			setError(null);
		} else setError(res.error);
	}, [gateway]);
	useEffect(() => void refresh(), [refresh]);

	const confirm = async () => {
		const action = pending;
		setPending(null);
		setBusy(true);
		const res = action === 'set' ? await setWebhookNow(gateway, drop) : await deleteWebhookNow(gateway, drop);
		setBusy(false);
		if (res.ok) {
			setHook(res.data.webhook);
			setError(null);
			toast.success(action === 'set' ? 'Webhook set' : 'Webhook deleted');
		} else setError(res.error);
		setDrop(false);
	};

	return (
		<Card>
			<CardHeader>
				<CardTitle className="text-base">Webhook</CardTitle>
				<CardDescription>The address Telegram sends this bot's messages to.</CardDescription>
			</CardHeader>
			<CardContent className="space-y-4">
				{error && <p role="alert" className="text-sm text-destructive">{error}</p>}
				{hook && (
					<>
						<CopyField label="Expected address" value={hook.expected_url} />
						<dl className="space-y-2">
							<Row label="Current address">{hook.url || 'None set'}</Row>
							<Row label="Matches this site">
								<Badge variant={hook.url_matches ? 'pill-success' : 'pill-danger'}>{hook.url_matches ? 'Yes' : 'No'}</Badge>
							</Row>
							<Row label="Waiting updates">{hook.pending_update_count}</Row>
							<Row label="Last error">{hook.last_error_message || 'None'}</Row>
							<Row label="Update types">
								{hook.allowed_updates_ok ? 'All required types' : 'Missing some types'}
								{hook.allowed_updates ? ` (${hook.allowed_updates.length}/${hook.expected_allowed_updates.length})` : ''}
							</Row>
						</dl>
					</>
				)}
				<div className="flex flex-wrap gap-2">
					<Button onClick={() => setPending('set')} disabled={busy}>Set webhook</Button>
					<Button variant="outline" onClick={() => setPending('delete')} disabled={busy || !hook?.url}>Delete webhook</Button>
					<Button variant="ghost" onClick={refresh} disabled={busy}>Refresh</Button>
				</div>
			</CardContent>
			<AlertDialog open={pending !== null} onOpenChange={(o) => !o && setPending(null)}>
				<AlertDialogContent>
					<AlertDialogHeader>
						<AlertDialogTitle>{pending === 'set' ? 'Take over this bot?' : 'Stop receiving messages here?'}</AlertDialogTitle>
						<AlertDialogDescription>
							{pending === 'set'
								? 'Telegram delivers a bot\'s messages to one address only. Setting the webhook sends all of this bot\'s messages to this site and stops delivery anywhere else.'
								: 'Telegram will stop sending this bot\'s messages to this site until you set the webhook again.'}
						</AlertDialogDescription>
					</AlertDialogHeader>
					<div className="flex items-center gap-2">
						<Switch id="tg-drop-pending" checked={drop} onCheckedChange={setDrop} />
						<Label htmlFor="tg-drop-pending">Discard messages that are waiting</Label>
					</div>
					<AlertDialogFooter>
						<AlertDialogCancel>Cancel</AlertDialogCancel>
						<AlertDialogAction onClick={confirm}>{pending === 'set' ? 'Set webhook' : 'Delete webhook'}</AlertDialogAction>
					</AlertDialogFooter>
				</AlertDialogContent>
			</AlertDialog>
		</Card>
	);
}
