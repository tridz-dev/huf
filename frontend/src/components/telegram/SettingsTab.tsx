import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { Switch } from '@/components/ui/switch';
import { Checkbox } from '@/components/ui/checkbox';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { Textarea } from '@/components/ui/textarea';
import { LoadError } from '@/components/whatsapp/BridgeUnavailable';
import { getAvailableAgents } from '@/services/gatewayApi';
import { getFlowDefinitions } from '@/services/flowApi';
import { listTemplates } from '@/services/telegramTemplatesApi';
import {
	getTelegramSettings,
	listGatewayUsers,
	updateTelegramSettings,
	type TelegramSettings,
	type TelegramSettingValue,
} from '@/services/telegramSettingsApi';
import {
	activeWarning,
	dirtyValues,
	hasInvalidNumber,
	hasWebAccessErrors,
	webAccessErrors,
	webHoursWarning,
	isVisible,
	SETTINGS_SECTIONS,
	toDraft,
	type FieldDef,
	type SectionDef,
	type SettingsDraft,
} from './settingsModel';
import { WebAccessLinkHelper } from './WebAccessLinkHelper';
import { cn } from '@/lib/utils';
import type { TelegramTabProps } from './tabTypes';

interface PickerOption { value: string; label: string }
type Pickers = Partial<Record<'template' | 'agent' | 'flow' | 'user', PickerOption[]>>;

const NONE = '__none__';

interface FieldProps {
	field: FieldDef;
	value: TelegramSettingValue | undefined;
	saved: TelegramSettingValue | undefined;
	pickers: Pickers;
	options: string[];
	disabled: boolean;
	onChange: (value: TelegramSettingValue) => void;
}

function Field({ field, value, saved, pickers, options, disabled, onChange }: FieldProps) {
	const id = `tg-${field.name}`;
	const warning = activeWarning(field, value, saved);
	const control = (() => {
		switch (field.kind) {
			case 'switch':
				return <Switch id={id} checked={value === true} disabled={disabled} onCheckedChange={onChange} />;
			case 'select':
				return (
					<Select
						value={field.allowEmpty && !value ? NONE : String(value ?? '')}
						disabled={disabled}
						onValueChange={(v) => onChange(v === NONE ? '' : v)}
					>
						<SelectTrigger id={id} className="w-full sm:w-72">
							<SelectValue />
						</SelectTrigger>
						<SelectContent>
							{field.allowEmpty && <SelectItem value={NONE}>Not set</SelectItem>}
							{options.map((o) => (
								<SelectItem key={o} value={o}>{field.optionLabels?.[o] ?? o}</SelectItem>
							))}
						</SelectContent>
					</Select>
				);
			case 'number':
				return (
					<Input
						id={id}
						type="number"
						min={field.min ?? 0}
						className="w-full sm:w-40"
						value={value === '' || value === undefined ? '' : String(value)}
						disabled={disabled}
						onChange={(e) => onChange(e.target.value === '' ? '' : Number(e.target.value))}
					/>
				);
			case 'lines':
				return (
					<Textarea id={id} rows={3} placeholder={field.placeholder} value={String(value ?? '')} disabled={disabled} onChange={(e) => onChange(e.target.value)} />
				);
			case 'text':
				return (
					<Textarea id={id} rows={2} value={String(value ?? '')} disabled={disabled} onChange={(e) => onChange(e.target.value)} />
				);
			case 'template':
			case 'agent':
			case 'flow':
			case 'user': {
				const current = String(value ?? '');
				const list = pickers[field.kind] ?? [];
				const known = list.some((o) => o.value === current);
				return (
					<select
						id={id}
						value={current}
						disabled={disabled}
						onChange={(e) => onChange(e.target.value)}
						className="h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm sm:w-72"
					>
						<option value="">{field.kind === 'user' ? 'Choose a user' : 'None'}</option>
						{current && !known && <option value={current}>{current}</option>}
						{list.map((o) => (
							<option key={o.value} value={o.value}>{o.label}</option>
						))}
					</select>
				);
			}
		}
	})();
	const inline = field.kind === 'switch';
	return (
		<div className={inline ? 'flex items-start justify-between gap-4' : 'space-y-1.5'}>
			<div className="space-y-0.5">
				<Label htmlFor={id} className="text-sm text-ink">{field.label}</Label>
				{field.help && <p className="text-xs text-steel">{field.help}</p>}
				{warning && <p role="note" className={cn('text-xs', field.tone === 'danger' ? 'text-destructive' : 'text-warning')}>{warning}</p>}
			</div>
			{control}
		</div>
	);
}

interface WebAccessSectionProps {
	section: SectionDef;
	gateway: string;
	draft: SettingsDraft;
	saved: SettingsDraft;
	unavailable: string[];
	disabled: boolean;
	onChange: (name: string, value: TelegramSettingValue) => void;
}

function WebAccessSection({ section, gateway, draft, saved, unavailable, disabled, onChange }: WebAccessSectionProps) {
	const [advancedOpen, setAdvancedOpen] = useState(false);
	const fields = section.fields.filter((f) => !unavailable.includes(f.name));
	if (fields.length === 0) return null;
	const has = (n: string) => fields.some((f) => f.name === n);
	const def = (n: string) => fields.find((f) => f.name === n)!;
	const errors = webAccessErrors(draft);
	const enabled = draft.telegram_web_access_enabled === true;
	const hoursWarning = webHoursWarning(draft.telegram_web_session_hours);
	const checkbox = (n: string) => {
		const f = def(n);
		const warning = activeWarning(f, draft[n], saved[n]);
		return (
			<div className="flex items-start gap-3">
				<Checkbox id={`tg-${n}`} checked={draft[n] === true} disabled={disabled} onCheckedChange={(c) => onChange(n, c === true)} className="mt-0.5" />
				<div className="space-y-0.5">
					<Label htmlFor={`tg-${n}`} className="text-sm text-ink">{f.label}</Label>
					{f.help && <p className="text-xs text-steel">{f.help}</p>}
					{warning && <p role="note" className={cn('text-xs', f.tone === 'danger' ? 'text-destructive' : 'text-warning')}>{warning}</p>}
				</div>
			</div>
		);
	};
	const advanced = fields.filter((f) => f.advanced);
	return (
		<Card>
			<CardHeader>
				<CardTitle className="text-sm">{section.title}</CardTitle>
				<CardDescription>{section.description}</CardDescription>
			</CardHeader>
			<CardContent className="space-y-4">
				{has('telegram_web_access_enabled') && (
					<div className="space-y-2">
						<div className="flex items-center justify-between gap-4">
							<Label htmlFor="tg-telegram_web_access_enabled" className="text-sm text-ink">{def('telegram_web_access_enabled').label}</Label>
							<Switch id="tg-telegram_web_access_enabled" checked={enabled} disabled={disabled} onCheckedChange={(c) => onChange('telegram_web_access_enabled', c)} />
						</div>
						{enabled && (
							<div role="note" className="rounded-md border border-destructive p-3 text-xs text-destructive">
								{def('telegram_web_access_enabled').warning}
							</div>
						)}
					</div>
				)}
				{has('telegram_web_allowed_paths') && (
					<div className="space-y-1.5">
						<Label htmlFor="tg-telegram_web_allowed_paths" className="text-sm text-ink">{def('telegram_web_allowed_paths').label}</Label>
						<Textarea
							id="tg-telegram_web_allowed_paths"
							rows={3}
							placeholder={def('telegram_web_allowed_paths').placeholder}
							value={String(draft.telegram_web_allowed_paths ?? '')}
							disabled={disabled}
							onChange={(e) => onChange('telegram_web_allowed_paths', e.target.value)}
						/>
						<p className="text-xs text-steel">{def('telegram_web_allowed_paths').help}</p>
						{errors.paths && <p role="alert" className="text-xs text-destructive">{errors.paths}</p>}
					</div>
				)}
				{has('telegram_web_session_hours') && (
					<div className="space-y-1.5">
						<Label htmlFor="tg-telegram_web_session_hours" className="text-sm text-ink">{def('telegram_web_session_hours').label}</Label>
						<Input
							id="tg-telegram_web_session_hours"
							type="number"
							min={1}
							max={720}
							className="w-full sm:w-40"
							value={draft.telegram_web_session_hours === '' || draft.telegram_web_session_hours === undefined ? '' : String(draft.telegram_web_session_hours)}
							disabled={disabled}
							onChange={(e) => onChange('telegram_web_session_hours', e.target.value === '' ? '' : Number(e.target.value))}
						/>
						{hoursWarning && <p role="note" className="text-xs text-warning">{hoursWarning}</p>}
						{errors.hours && <p role="alert" className="text-xs text-destructive">{errors.hours}</p>}
					</div>
				)}
				{has('telegram_web_allow_privileged') && checkbox('telegram_web_allow_privileged')}
				{has('telegram_web_allow_writes') && checkbox('telegram_web_allow_writes')}
				{advanced.length > 0 && (
					<Collapsible open={advancedOpen} onOpenChange={setAdvancedOpen}>
						<CollapsibleTrigger asChild>
							<Button type="button" variant="ghost" size="sm">{advancedOpen ? 'Hide advanced' : 'Advanced'}</Button>
						</CollapsibleTrigger>
						<CollapsibleContent className="space-y-1.5 pt-2">
							{advanced.map((f) => (
								<div key={f.name} className="space-y-1.5">
									<Label htmlFor={`tg-${f.name}`} className="text-sm text-ink">{f.label}</Label>
									<Textarea id={`tg-${f.name}`} rows={3} value={String(draft[f.name] ?? '')} disabled={disabled} onChange={(e) => onChange(f.name, e.target.value)} />
									{f.help && <p className="text-xs text-steel">{f.help}</p>}
								</div>
							))}
						</CollapsibleContent>
					</Collapsible>
				)}
				<WebAccessLinkHelper gateway={gateway} />
			</CardContent>
		</Card>
	);
}

/** Editable bot settings for one gateway. Saves only the fields that changed. */
export function SettingsTab({ gateway }: TelegramTabProps) {
	const [settings, setSettings] = useState<TelegramSettings | null>(null);
	const [saved, setSaved] = useState<SettingsDraft>({});
	const [draft, setDraft] = useState<SettingsDraft>({});
	const [error, setError] = useState('');
	const [saving, setSaving] = useState(false);
	const [saveError, setSaveError] = useState('');
	const [pickers, setPickers] = useState<Pickers>({});

	const apply = useCallback((s: TelegramSettings) => {
		setSettings(s);
		setSaved(toDraft(s));
		setDraft(toDraft(s));
	}, []);

	const load = useCallback(async () => {
		setError('');
		setSettings(null);
		const res = await getTelegramSettings(gateway);
		if (res.ok) apply(res.data);
		else setError(res.error);
	}, [gateway, apply]);
	useEffect(() => { void load(); }, [load]);

	// Pickers are best effort: if a list fails to load, the field still shows its saved value.
	useEffect(() => {
		let live = true;
		void Promise.all([
			listTemplates(gateway),
			getAvailableAgents(),
			getFlowDefinitions().catch(() => []),
			listGatewayUsers(gateway),
		]).then(([t, a, f, u]) => {
			if (!live) return;
			setPickers({
				template: t.ok ? t.data.filter((x) => x.is_active).map((x) => ({ value: x.name, label: x.template_name || x.name })) : [],
				agent: a.map((x) => ({ value: x.name, label: x.agent_name })),
				flow: f.map((x) => ({ value: x.name, label: x.flow_name || x.name })),
				user: u.ok ? u.data.map((x) => ({ value: x.name, label: x.full_name && x.full_name !== x.name ? `${x.full_name} (${x.name})` : x.name })) : [],
			});
		});
		return () => { live = false; };
	}, [gateway]);

	if (error) return <LoadError message={error} onRetry={load} />;
	if (!settings) return <Skeleton className="h-64" />;

	const dirty = dirtyValues(saved, draft);
	const dirtyCount = Object.keys(dirty).length;
	const invalid = hasInvalidNumber(draft) || hasWebAccessErrors(draft);

	const onSave = async () => {
		setSaving(true);
		setSaveError('');
		const res = await updateTelegramSettings(gateway, dirty);
		setSaving(false);
		if (!res.ok) {
			setSaveError(res.error);
			toast.error(res.error);
			return;
		}
		apply(res.data);
		toast.success('Settings saved.');
	};

	return (
		<div className="space-y-4">
			{SETTINGS_SECTIONS.map((section) => {
				if (section.id === 'web') {
					return (
						<WebAccessSection
							key={section.id}
							section={section}
							gateway={gateway}
							draft={draft}
							saved={saved}
							unavailable={settings.unavailable}
							disabled={saving}
							onChange={(name, v) => setDraft((d) => ({ ...d, [name]: v }))}
						/>
					);
				}
				const fields = section.fields.filter((f) => !settings.unavailable.includes(f.name) && isVisible(f, draft));
				if (fields.length === 0) return null;
				return (
					<Card key={section.id}>
						<CardHeader>
							<CardTitle className="text-sm">{section.title}</CardTitle>
							<CardDescription>{section.description}</CardDescription>
						</CardHeader>
						<CardContent className="space-y-4">
							{fields.map((f) => (
								<Field
									key={f.name}
									field={f}
									value={draft[f.name]}
									saved={saved[f.name]}
									pickers={pickers}
									options={settings.options[f.name] ?? []}
									disabled={saving}
									onChange={(v) => setDraft((d) => ({ ...d, [f.name]: v }))}
								/>
							))}
						</CardContent>
					</Card>
				);
			})}
			{saveError && <p role="alert" className="text-sm text-destructive">{saveError}</p>}
			<div className="sticky bottom-0 flex items-center justify-end gap-2 border-t border-line bg-background py-3">
				{dirtyCount > 0 && <span className="mr-auto text-xs text-steel">{dirtyCount === 1 ? '1 unsaved change' : `${dirtyCount} unsaved changes`}</span>}
				<Button variant="outline" disabled={dirtyCount === 0 || saving} onClick={() => setDraft(saved)}>
					Discard
				</Button>
				<Button disabled={dirtyCount === 0 || invalid || saving} onClick={onSave}>
					{saving ? 'Saving…' : 'Save changes'}
				</Button>
			</div>
		</div>
	);
}
