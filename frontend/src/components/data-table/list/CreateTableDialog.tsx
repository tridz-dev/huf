import { useState } from 'react';
import { ClipboardPaste, FileSpreadsheet, Sparkles, Table2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Field } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { TemplateChips, type TemplateChip } from '@/components/builder';
import { nameError } from './tableListModel';

export type TableStart = 'blank' | 'csv' | 'paste' | 'describe';

const STARTS: TemplateChip[] = [
	{ id: 'blank', label: 'Blank', icon: <Table2 className="h-3.5 w-3.5" /> },
	{ id: 'csv', label: 'CSV or Sheet', icon: <FileSpreadsheet className="h-3.5 w-3.5" /> },
	{ id: 'paste', label: 'Paste', icon: <ClipboardPaste className="h-3.5 w-3.5" /> },
	{ id: 'describe', label: 'Describe', icon: <Sparkles className="h-3.5 w-3.5" /> },
];

export interface CreateTableDialogProps {
	open: boolean;
	onOpenChange: (open: boolean) => void;
	existingNames: string[];
	initialStart?: TableStart;
	onCreate: (input: { name: string; description: string; start: TableStart }) => Promise<void>;
}

/** One-modal create (mockup state 3): name, optional description, how to start. */
export function CreateTableDialog({ open, onOpenChange, existingNames, initialStart = 'blank', onCreate }: CreateTableDialogProps) {
	const [name, setName] = useState('');
	const [description, setDescription] = useState('');
	const [start, setStart] = useState<TableStart>(initialStart);
	const [busy, setBusy] = useState(false);
	const [failure, setFailure] = useState<string | null>(null);
	const error = nameError(name.trim(), existingNames);
	const ready = name.trim().length > 0 && !error && !busy;

	const submit = async () => {
		if (!ready) return;
		setBusy(true);
		setFailure(null);
		try {
			await onCreate({ name: name.trim(), description: description.trim(), start });
		} catch (e) {
			setFailure(e instanceof Error ? e.message : 'Could not create the table.');
		} finally {
			setBusy(false);
		}
	};

	return (
		<Dialog open={open} onOpenChange={onOpenChange}>
			<DialogContent>
				<form
					className="space-y-4"
					onSubmit={(e) => {
						e.preventDefault();
						void submit();
					}}
				>
					<DialogHeader>
						<DialogTitle>New table</DialogTitle>
						<DialogDescription>Name it, then choose how to fill it. You can change everything later.</DialogDescription>
					</DialogHeader>
					<Field label="Name" required error={error ?? failure ?? undefined} hint="Letters, numbers, spaces, - and _">
						<Input autoFocus value={name} placeholder="Customers" onChange={(e) => setName(e.target.value)} />
					</Field>
					<Field label="Description (optional)" hint="What this table holds. Agents read this.">
						<Textarea rows={2} value={description} onChange={(e) => setDescription(e.target.value)} />
					</Field>
					<TemplateChips label="Start with" items={STARTS} activeId={start} onPick={(id) => setStart(id as TableStart)} />
					<DialogFooter>
						<Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
							Cancel
						</Button>
						<Button type="submit" disabled={!ready}>
							{busy ? 'Creating…' : 'Create table'}
						</Button>
					</DialogFooter>
				</form>
			</DialogContent>
		</Dialog>
	);
}
