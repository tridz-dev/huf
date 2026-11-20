import { Button } from '@/components/ui/button';
import { StepHint, DropZone } from '@/components/patterns';
import { TemplateChips } from '@/components/builder';
import type { TableStart } from './CreateTableDialog';

const STEPS = [
	{ title: 'Name your table', description: 'Say what it holds.' },
	{ title: 'Add rows', description: 'Import a file, paste, or type.' },
	{ title: 'Let an agent use it', description: 'Choose what each agent may do.' },
];

const STARTS = [
	{ id: 'blank', label: 'Blank table' },
	{ id: 'csv', label: 'From a CSV or Sheet' },
	{ id: 'paste', label: 'Paste rows' },
	{ id: 'describe', label: 'Describe it' },
];

/** Empty state (mockup state 2, §6.10.8): steps, a drop target, template starts. */
export function EmptyTables({ onStart, onNew }: { onStart: (start: TableStart) => void; onNew: () => void }) {
	return (
		<div className="space-y-6" data-testid="tables-empty">
			<StepHint steps={STEPS} current={0} />
			<DropZone
				title="No tables yet"
				hint="Drop a CSV or Excel file to make a table from it, or start from scratch."
				accept=".csv,.xlsx,.xls"
				onFiles={() => onStart('csv')}
				actions={<Button onClick={onNew}>New table</Button>}
			/>
			<TemplateChips label="Start with" items={STARTS} onPick={(id) => onStart(id as TableStart)} />
		</div>
	);
}
