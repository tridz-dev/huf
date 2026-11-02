import { useCallback, useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';
import { Loader2, Plus, Search, Send, Trash2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import {
	AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
	AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { LoadError } from '@/components/whatsapp/BridgeUnavailable';
import { cn } from '@/lib/utils';
import {
	deleteTemplate, emptyDraft, filterTemplates, getTemplate, listTemplates, mediaTypeLabel, problemsByField, saveTemplate,
	type TemplateDraft, type TemplateSummary,
} from '@/services/telegramTemplatesApi';
import { SendTestDialog } from './SendTestDialog';
import { TemplateEditor } from './TemplateEditor';

export interface TemplatesTabProps {
	gateway?: string;
	/** Telegram gateways a template can be limited to (optional). */
	gateways?: string[];
}

export function TemplatesTab({ gateway, gateways }: TemplatesTabProps) {
	const [rows, setRows] = useState<TemplateSummary[]>([]);
	const [loading, setLoading] = useState(true);
	const [error, setError] = useState('');
	const [search, setSearch] = useState('');
	const [selected, setSelected] = useState('');
	const [draft, setDraft] = useState<TemplateDraft | null>(null);
	const [saved, setSaved] = useState<TemplateDraft | null>(null);
	const [opening, setOpening] = useState(false);
	const [saving, setSaving] = useState(false);
	const [serverErrors, setServerErrors] = useState<Record<string, string>>({});
	const [toDelete, setToDelete] = useState(false);
	const [testing, setTesting] = useState(false);

	const load = useCallback(async () => {
		setLoading(true);
		setError('');
		const res = await listTemplates(gateway);
		if (res.ok) setRows(res.data);
		else setError(res.error);
		setLoading(false);
	}, [gateway]);
	useEffect(() => { void load(); }, [load]);

	const visible = useMemo(() => filterTemplates(rows, search), [rows, search]);

	const open = async (name: string) => {
		setSelected(name);
		setOpening(true);
		setServerErrors({});
		const res = await getTemplate(name);
		setOpening(false);
		if (res.ok) { setDraft(res.data); setSaved(res.data); }
		else { toast.error(res.error); setDraft(null); }
	};
	const create = () => {
		setSelected('');
		setServerErrors({});
		setSaved(null);
		setDraft(emptyDraft(gateway ?? ''));
	};
	const close = () => { setDraft(null); setSaved(null); setSelected(''); setServerErrors({}); };

	const save = async () => {
		if (!draft) return;
		setSaving(true);
		setServerErrors({});
		const res = await saveTemplate(draft);
		setSaving(false);
		if (res.ok) {
			toast.success('Template saved');
			setDraft(res.template);
			setSaved(res.template);
			setSelected(res.template.name ?? '');
			void load();
		} else {
			const errs = problemsByField(res.problems);
			setServerErrors(Object.keys(errs).length ? errs : { form: res.error });
		}
	};

	const remove = async () => {
		if (!draft?.name) return;
		const res = await deleteTemplate(draft.name);
		setToDelete(false);
		if (res.ok) { toast.success('Template deleted'); close(); void load(); }
		else toast.error(res.error);
	};

	return (
		<div className="grid gap-4 lg:grid-cols-[300px_1fr]">
			<div className="space-y-3">
				<div className="flex gap-2">
					<div className="relative flex-1">
						<Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-steel" aria-hidden />
						<Input aria-label="Search templates" className="pl-8" placeholder="Search templates" value={search} onChange={(e) => setSearch(e.target.value)} />
					</div>
					<Button onClick={create}><Plus className="mr-1 h-4 w-4" />New</Button>
				</div>
				{error ? (
					<LoadError message={error} onRetry={load} />
				) : loading ? (
					<div className="space-y-2" aria-hidden><Skeleton className="h-14" /><Skeleton className="h-14" /></div>
				) : visible.length === 0 ? (
					<p className="rounded-md border border-dashed border-line p-4 text-center text-sm text-steel">
						{rows.length === 0 ? 'No templates yet. Create one to reuse messages with buttons and media.' : 'No templates match your search.'}
					</p>
				) : (
					<ul className="space-y-1.5">
						{visible.map((r) => (
							<li key={r.name}>
								<button
									type="button"
									onClick={() => void open(r.name)}
									aria-current={selected === r.name}
									className={cn('w-full rounded-md border px-3 py-2 text-left hover:bg-paper-deep', selected === r.name ? 'border-signal bg-paper-deep' : 'border-line')}
								>
									<div className="flex items-center justify-between gap-2">
										<span className="truncate text-sm font-medium text-ink">{r.template_name}</span>
										{!Number(r.is_active) && <Badge variant="outline">Off</Badge>}
									</div>
									<p className="truncate text-xs text-steel">
										{[r.language, r.parse_mode, r.media_type !== 'none' ? mediaTypeLabel(r.media_type) : '', r.gateway || 'All bots'].filter(Boolean).join(' · ')}
									</p>
								</button>
							</li>
						))}
					</ul>
				)}
			</div>

			<div className="min-w-0 rounded-md border border-line p-4">
				{opening ? (
					<div className="flex justify-center py-12"><Loader2 className="h-5 w-5 animate-spin text-steel" aria-label="Loading template" /></div>
				) : draft ? (
					<div className="space-y-4">
						<div className="flex items-center justify-between gap-2">
							<h2 className="text-base font-semibold text-ink">{draft.name ? draft.template_name : 'New template'}</h2>
							{draft.name && (
								<div className="flex gap-2">
									<Button variant="outline" size="sm" disabled={!gateway} onClick={() => setTesting(true)}><Send className="mr-1 h-3.5 w-3.5" />Send test</Button>
									<Button variant="outline" size="sm" onClick={() => setToDelete(true)}><Trash2 className="mr-1 h-3.5 w-3.5" />Delete</Button>
								</div>
							)}
						</div>
						<TemplateEditor draft={draft} onChange={setDraft} onSave={save} onCancel={close} saving={saving} serverErrors={serverErrors} gateways={gateways} />
					</div>
				) : (
					<p className="py-12 text-center text-sm text-steel">Choose a template to edit, or create a new one.</p>
				)}
			</div>

			<SendTestDialog template={testing ? saved : null} gateway={gateway ?? ''} onClose={() => setTesting(false)} />
			<AlertDialog open={toDelete} onOpenChange={setToDelete}>
				<AlertDialogContent>
					<AlertDialogHeader>
						<AlertDialogTitle>Delete this template?</AlertDialogTitle>
						<AlertDialogDescription>Bots that use it as a default or welcome message will stop sending it.</AlertDialogDescription>
					</AlertDialogHeader>
					<AlertDialogFooter>
						<AlertDialogCancel>Keep</AlertDialogCancel>
						<AlertDialogAction onClick={() => void remove()}>Delete</AlertDialogAction>
					</AlertDialogFooter>
				</AlertDialogContent>
			</AlertDialog>
		</div>
	);
}
