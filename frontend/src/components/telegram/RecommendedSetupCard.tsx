import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';

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
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { applyRecommendedSetup, getRecommendedSetup, type BotCommand, type RecommendedPlan } from '@/services/telegramCommandsApi';

const names = (cmds: BotCommand[]) => (cmds.length ? cmds.map((c) => `/${c.command}`).join(' ') : 'none');

export function RecommendedSetupCard({ gateway, onApplied }: { gateway: string; onApplied?: () => void }) {
	const [plan, setPlan] = useState<RecommendedPlan | null>(null);
	const [error, setError] = useState<string | null>(null);
	const [confirming, setConfirming] = useState(false);
	const [busy, setBusy] = useState(false);

	const load = useCallback(async () => {
		const res = await getRecommendedSetup(gateway);
		if (res.ok) {
			setPlan(res.data.plan);
			setError(null);
		} else setError(res.error);
	}, [gateway]);
	useEffect(() => void load(), [load]);

	const apply = async () => {
		setBusy(true);
		const res = await applyRecommendedSetup(gateway, Boolean(plan?.menu_button.https_ok), true);
		setBusy(false);
		setConfirming(false);
		if (res.ok) {
			toast.success('Recommended setup applied');
			void load();
			onApplied?.();
		} else toast.error(res.error);
	};

	const menu = plan?.menu_button;
	const menuLabel = (b: { type: string; text?: string }) => (b.type === 'web_app' ? `${b.text ?? 'Web app'} (web app)` : b.type === 'commands' ? 'Command list' : 'Telegram default');

	return (
		<Card>
			<CardHeader>
				<CardTitle className="text-base">Recommended setup</CardTitle>
				<CardDescription>Publish the standard commands and a Console button that opens the Huf app inside Telegram.</CardDescription>
			</CardHeader>
			<CardContent className="space-y-3 text-sm">
				{error && <p role="alert" className="text-destructive">{error}</p>}
				{plan?.commands.map((c) => (
					<div key={c.scope} className="space-y-0.5">
						<p className="font-medium text-ink">{c.scope === 'default' ? 'Commands' : 'Group commands'}</p>
						<p className="text-steel">Now: {names(c.current)}</p>
						<p className="text-ink">New: {names(c.recommended)}</p>
					</div>
				))}
				{menu && (
					<div className="space-y-0.5">
						<p className="font-medium text-ink">Menu button</p>
						<p className="text-steel">Now: {menuLabel(menu.current)}</p>
						<p className="text-ink">New: {menuLabel(menu.recommended)}</p>
					</div>
				)}
				{menu && !menu.https_ok && <p role="alert" className="text-amber-600">{menu.warning}</p>}
			</CardContent>
			<CardFooter>
				<Button onClick={() => setConfirming(true)} disabled={!plan || busy}>Apply</Button>
			</CardFooter>
			<AlertDialog open={confirming} onOpenChange={setConfirming}>
				<AlertDialogContent>
					<AlertDialogHeader>
						<AlertDialogTitle>Apply recommended setup?</AlertDialogTitle>
						<AlertDialogDescription>
							This replaces the commands currently published for this bot
							{menu?.https_ok ? ' and changes its menu button to Console' : ''}. You can restore the old list by hand from the editor below.
						</AlertDialogDescription>
					</AlertDialogHeader>
					<AlertDialogFooter>
						<AlertDialogCancel>Cancel</AlertDialogCancel>
						<AlertDialogAction onClick={(e) => { e.preventDefault(); void apply(); }} disabled={busy}>{busy ? 'Applying...' : 'Replace and apply'}</AlertDialogAction>
					</AlertDialogFooter>
				</AlertDialogContent>
			</AlertDialog>
		</Card>
	);
}
