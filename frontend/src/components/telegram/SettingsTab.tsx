import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';
import { LoadError } from '@/components/whatsapp/BridgeUnavailable';
import {
	getTelegramSettings,
	updateTelegramSettings,
	type TelegramSettings,
	type TelegramSettingValue,
} from '@/services/telegramSettingsApi';
import {
	activeWarning,
	dirtyValues,
	hasInvalidNumber,
	isVisible,
	SETTINGS_SECTIONS,
	TEMPLATES_COMING_SOON,
	toDraft,
	type FieldDef,
	type SettingsDraft,
} from './settingsModel';
import type { TelegramTabProps } from './tabTypes';

interface FieldProps {
	field: FieldDef;
	value: TelegramSettingValue | undefined;
	options: string[];
	disabled: boolean;
	onChange: (value: TelegramSettingValue) => void;
}

function Field({ field, value, options, disabled, onChange }: FieldProps) {
	const id = `tg-${field.name}`;
	const warning = activeWarning(field, value);
	const control = (() => {
		switch (field.kind) {
			case 'switch':
				return <Switch id={id} checked={value === true} disabled={disabled} onCheckedChange={onChange} />;
			case 'select':
				return (
					<Select value={String(value ?? '')} disabled={disabled} onValueChange={onChange}>
						<SelectTrigger id={id} className="w-full sm:w-72">
							<SelectValue />
						</SelectTrigger>
						<SelectContent>
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
			case 'text':
				return (
					<Textarea id={id} rows={2} value={String(value ?? '')} disabled={disabled} onChange={(e) => onChange(e.target.value)} />
				);
			case 'template':
				return <Input id={id} value={String(value ?? '')} disabled placeholder={TEMPLATES_COMING_SOON} />;
		}
	})();
	const inline = field.kind === 'switch';
	return (
		<div className={inline ? 'flex items-start justify-between gap-4' : 'space-y-1.5'}>
			<div className="space-y-0.5">
				<Label htmlFor={id} className="text-sm text-ink">{field.label}</Label>
				{field.help && <p className="text-xs text-steel">{field.help}</p>}
				{field.kind === 'template' && <p className="text-xs text-steel">{TEMPLATES_COMING_SOON}</p>}
				{warning && <p role="note" className="text-xs text-warning">{warning}</p>}
			</div>
			{control}
		</div>
	);
}

/** Editable bot settings for one gateway. Saves only the fields that changed. */
export function SettingsTab({ gateway }: TelegramTabProps) {
	const [settings, setSettings] = useState<TelegramSettings | null>(null);
	const [saved, setSaved] = useState<SettingsDraft>({});
	const [draft, setDraft] = useState<SettingsDraft>({});
	const [error, setError] = useState('');
	const [saving, setSaving] = useState(false);

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

	if (error) return <LoadError message={error} onRetry={load} />;
	if (!settings) return <Skeleton className="h-64" />;

	const dirty = dirtyValues(saved, draft);
	const dirtyCount = Object.keys(dirty).length;
	const invalid = hasInvalidNumber(draft);

	const onSave = async () => {
		setSaving(true);
		const res = await updateTelegramSettings(gateway, dirty);
		setSaving(false);
		if (!res.ok) {
			toast.error(res.error);
			return;
		}
		apply(res.data);
		toast.success('Settings saved.');
	};

	return (
		<div className="space-y-4">
			{SETTINGS_SECTIONS.map((section) => {
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
									options={settings.options[f.name] ?? []}
									disabled={saving}
									onChange={(v) => setDraft((d) => ({ ...d, [f.name]: v }))}
								/>
							))}
						</CardContent>
					</Card>
				);
			})}
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
