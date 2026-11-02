import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { getBotProfile, PROFILE_LIMITS, setBotProfile, validateProfile, type BotProfile } from '@/services/telegramCommandsApi';

const EMPTY: BotProfile = { name: '', description: '', short_description: '' };

/** Bot name, "About" text and the description shown in an empty chat. */
export function ProfileCard({ gateway }: { gateway: string }) {
	const [saved, setSaved] = useState<BotProfile>(EMPTY);
	const [draft, setDraft] = useState<BotProfile>(EMPTY);
	const [loading, setLoading] = useState(true);
	const [saving, setSaving] = useState(false);
	const [error, setError] = useState<string | null>(null);

	const load = useCallback(async () => {
		setLoading(true);
		const res = await getBotProfile(gateway);
		if (res.ok) {
			setSaved(res.data.profile);
			setDraft(res.data.profile);
			setError(null);
		} else setError(res.error);
		setLoading(false);
	}, [gateway]);
	useEffect(() => void load(), [load]);

	const errors = validateProfile(draft);
	const dirty = (Object.keys(draft) as (keyof BotProfile)[]).some((k) => draft[k] !== saved[k]);
	const set = (k: keyof BotProfile) => (e: { target: { value: string } }) => setDraft((d) => ({ ...d, [k]: e.target.value }));

	const save = async () => {
		setSaving(true);
		const changed: Partial<BotProfile> = {};
		(Object.keys(draft) as (keyof BotProfile)[]).forEach((k) => {
			if (draft[k] !== saved[k]) changed[k] = draft[k];
		});
		const res = await setBotProfile(gateway, changed);
		setSaving(false);
		if (res.ok) {
			setSaved(draft);
			toast.success('Saved to Telegram');
		} else toast.error(res.error);
	};

	const field = (k: keyof BotProfile, label: string, help: string, multiline = false) => (
		<div className="space-y-1.5">
			<Label htmlFor={`tg-profile-${k}`}>{label}</Label>
			{multiline ? (
				<Textarea id={`tg-profile-${k}`} value={draft[k]} onChange={set(k)} rows={k === 'description' ? 4 : 2} disabled={loading} />
			) : (
				<Input id={`tg-profile-${k}`} value={draft[k]} onChange={set(k)} disabled={loading} />
			)}
			<p className={`text-xs ${errors[k] ? 'text-destructive' : 'text-steel'}`}>
				{errors[k] ?? help} ({draft[k].length}/{PROFILE_LIMITS[k]})
			</p>
		</div>
	);

	return (
		<Card>
			<CardHeader>
				<CardTitle className="text-base">Bot profile</CardTitle>
				<CardDescription>How the bot appears in Telegram. Changes are sent to Telegram when you save.</CardDescription>
			</CardHeader>
			<CardContent className="space-y-4">
				{error && <p role="alert" className="text-sm text-destructive">{error}</p>}
				{field('name', 'Name', 'Shown at the top of the chat.')}
				{field('short_description', 'About', 'Shown on the bot profile page.', true)}
				{field('description', 'Description', 'Shown when someone opens an empty chat with the bot.', true)}
			</CardContent>
			<CardFooter>
				<Button onClick={save} disabled={!dirty || saving || loading || Object.keys(errors).length > 0}>
					{saving ? 'Saving...' : 'Save to Telegram'}
				</Button>
			</CardFooter>
		</Card>
	);
}
