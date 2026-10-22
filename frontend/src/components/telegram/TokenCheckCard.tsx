import { useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { checkToken, type TokenCheck } from '@/services/telegramCommandsApi';

/** Asks Telegram whether it still accepts the saved bot token. The token itself is never shown. */
export function TokenCheckCard({ gateway }: { gateway: string }) {
	const [check, setCheck] = useState<TokenCheck | null>(null);
	const [error, setError] = useState<string | null>(null);
	const [busy, setBusy] = useState(false);

	const run = async () => {
		setBusy(true);
		const res = await checkToken(gateway);
		setBusy(false);
		if (res.ok) {
			setCheck(res.data.check);
			setError(null);
		} else setError(res.error);
	};

	return (
		<Card>
			<CardHeader>
				<CardTitle className="text-base">Bot token</CardTitle>
				<CardDescription>Whether Telegram still accepts this gateway's token.</CardDescription>
			</CardHeader>
			<CardContent className="space-y-3">
				{error && <p role="alert" className="text-sm text-destructive">{error}</p>}
				{!check ? (
					<p className="text-sm text-steel">Not checked yet.</p>
				) : check.valid ? (
					<p className="text-sm text-ink">
						<Badge variant="pill-success">Valid</Badge> {check.username ? `@${check.username}` : check.first_name}
					</p>
				) : (
					<div role="note" className="rounded border border-destructive/40 bg-destructive-tint px-3 py-2 text-sm text-ink">
						<Badge variant="pill-danger">Not valid</Badge> {check.reason || 'Telegram rejected this token.'} Replace it in Settings.
					</div>
				)}
				<Button variant="outline" onClick={run} disabled={busy}>{busy ? 'Checking...' : 'Check token'}</Button>
			</CardContent>
		</Card>
	);
}
