import { useCallback, useEffect, useState } from 'react';
import { Plus, Trash2 } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import {
	cleanCommands,
	COMMAND_SCOPES,
	deleteCommands,
	getCommands,
	getMenuButton,
	setCommands,
	setMenuButton,
	validateCommands,
	validateMenuButton,
	type BotCommand,
	type CommandScope,
	type MenuButtonType,
} from '@/services/telegramCommandsApi';
import { ProfileCard } from './ProfileCard';

const SELECT_CLASS = 'h-9 rounded-md border border-line bg-paper px-2 text-sm text-ink';

export function CommandsEditor({ gateway }: { gateway: string }) {
	const [scope, setScope] = useState<CommandScope>('default');
	const [language, setLanguage] = useState('');
	const [rows, setRows] = useState<BotCommand[]>([]);
	const [loading, setLoading] = useState(true);
	const [saving, setSaving] = useState(false);
	const [error, setError] = useState<string | null>(null);

	const load = useCallback(async () => {
		setLoading(true);
		const res = await getCommands(gateway, scope, language);
		if (res.ok) {
			setRows(res.data.commands.map((c) => ({ command: c.command, description: c.description, is_ephemeral: Boolean(c.is_ephemeral) })));
			setError(null);
		} else setError(res.error);
		setLoading(false);
	}, [gateway, scope, language]);
	useEffect(() => void load(), [load]);

	const errors = validateCommands(rows);
	const invalid = Object.keys(errors).length > 0 || rows.length === 0;
	const patch = (i: number, p: Partial<BotCommand>) => setRows((r) => r.map((x, j) => (j === i ? { ...x, ...p } : x)));

	const save = async () => {
		setSaving(true);
		const res = await setCommands(gateway, scope, language, cleanCommands(rows));
		setSaving(false);
		if (res.ok) toast.success('Saved to Telegram');
		else toast.error(res.error);
	};
	const clear = async () => {
		const res = await deleteCommands(gateway, scope, language);
		if (res.ok) {
			setRows([]);
			toast.success('Commands cleared');
		} else toast.error(res.error);
	};

	return (
		<Card>
			<CardHeader>
				<CardTitle className="text-base">Commands</CardTitle>
				<CardDescription>The / menu people see in Telegram. Each scope and language has its own list.</CardDescription>
			</CardHeader>
			<CardContent className="space-y-4">
				<div className="flex flex-wrap items-end gap-3">
					<div className="space-y-1.5">
						<Label htmlFor="tg-cmd-scope">Who sees it</Label>
						<select id="tg-cmd-scope" className={SELECT_CLASS} value={scope} onChange={(e) => setScope(e.target.value as CommandScope)}>
							{COMMAND_SCOPES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
						</select>
					</div>
					<div className="space-y-1.5">
						<Label htmlFor="tg-cmd-lang">Language (optional)</Label>
						<Input id="tg-cmd-lang" className="w-24" placeholder="en" maxLength={2} value={language} onChange={(e) => setLanguage(e.target.value.toLowerCase())} />
					</div>
				</div>
				{error && <p role="alert" className="text-sm text-destructive">{error}</p>}
				{errors[-1] && <p className="text-sm text-destructive">{errors[-1]}</p>}
				<ul className="space-y-2">
					{rows.map((r, i) => (
						<li key={i} className="space-y-1">
							<div className="flex flex-wrap items-center gap-2">
								<Input aria-label={`Command ${i + 1} name`} className="w-40" placeholder="help" value={r.command} onChange={(e) => patch(i, { command: e.target.value })} />
								<Input aria-label={`Command ${i + 1} description`} className="min-w-48 flex-1" placeholder="What it does" value={r.description} onChange={(e) => patch(i, { description: e.target.value })} />
								<div className="flex items-center gap-1.5">
									<Switch aria-label={`Command ${i + 1} only visible to sender`} checked={Boolean(r.is_ephemeral)} onCheckedChange={(v) => patch(i, { is_ephemeral: v })} />
									<span className="text-xs text-steel">Only sender sees reply</span>
								</div>
								<Button variant="ghost" size="icon" aria-label={`Remove command ${i + 1}`} onClick={() => setRows((x) => x.filter((_, j) => j !== i))}><Trash2 className="size-4" /></Button>
							</div>
							{errors[i] && <p role="alert" className="text-xs text-destructive">{errors[i]}</p>}
						</li>
					))}
					{!loading && rows.length === 0 && <li className="text-sm text-steel">No commands set for this scope.</li>}
				</ul>
				<Button variant="outline" size="sm" onClick={() => setRows((r) => [...r, { command: '', description: '' }])}><Plus className="size-4" /> Add command</Button>
			</CardContent>
			<CardFooter className="gap-2">
				<Button onClick={save} disabled={invalid || saving || loading}>{saving ? 'Saving...' : 'Save to Telegram'}</Button>
				<Button variant="ghost" onClick={clear} disabled={loading}>Clear this list</Button>
			</CardFooter>
		</Card>
	);
}

export function MenuButtonCard({ gateway }: { gateway: string }) {
	const [type, setType] = useState<MenuButtonType>('commands');
	const [text, setText] = useState('');
	const [url, setUrl] = useState('');
	const [saving, setSaving] = useState(false);

	useEffect(() => {
		void getMenuButton(gateway).then((res) => {
			if (!res.ok) return;
			const b = res.data.menu_button;
			setType(b.type);
			setText(b.text ?? '');
			setUrl(b.web_app?.url ?? '');
		});
	}, [gateway]);

	const problem = validateMenuButton(type, text, url);
	const save = async () => {
		setSaving(true);
		const res = await setMenuButton(gateway, type, text, url);
		setSaving(false);
		if (res.ok) toast.success('Saved to Telegram');
		else toast.error(res.error);
	};

	return (
		<Card>
			<CardHeader>
				<CardTitle className="text-base">Menu button</CardTitle>
				<CardDescription>The button next to the message box: the command list or a web app.</CardDescription>
			</CardHeader>
			<CardContent className="space-y-3">
				<div className="space-y-1.5">
					<Label htmlFor="tg-menu-type">Opens</Label>
					<select id="tg-menu-type" className={SELECT_CLASS} value={type} onChange={(e) => setType(e.target.value as MenuButtonType)}>
						<option value="commands">Command list</option>
						<option value="web_app">Web app</option>
						<option value="default">Telegram default</option>
					</select>
				</div>
				{type === 'web_app' && (
					<>
						<div className="space-y-1.5">
							<Label htmlFor="tg-menu-text">Button text</Label>
							<Input id="tg-menu-text" value={text} onChange={(e) => setText(e.target.value)} />
						</div>
						<div className="space-y-1.5">
							<Label htmlFor="tg-menu-url">Web app address</Label>
							<Input id="tg-menu-url" placeholder="https://" value={url} onChange={(e) => setUrl(e.target.value)} />
						</div>
					</>
				)}
				{problem && <p role="alert" className="text-xs text-destructive">{problem}</p>}
			</CardContent>
			<CardFooter>
				<Button onClick={save} disabled={Boolean(problem) || saving}>{saving ? 'Saving...' : 'Save to Telegram'}</Button>
			</CardFooter>
		</Card>
	);
}

/** "Commands & profile" tab. */
export function CommandsTab({ gateway }: { gateway: string }) {
	return (
		<div className="space-y-4">
			<CommandsEditor gateway={gateway} />
			<div className="grid items-start gap-4 lg:grid-cols-2">
				<ProfileCard gateway={gateway} />
				<MenuButtonCard gateway={gateway} />
			</div>
		</div>
	);
}
