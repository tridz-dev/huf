import { Columns, Folder, Minus, type LucideIcon } from 'lucide-react';
import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { friendlyTypeName, typeGlyph } from '@/data/fieldTypeLabels';
import type { DataTableFieldType } from '@/types/dataTable.types';

interface TypeOption { type: DataTableFieldType; label: string; icon: LucideIcon }
interface FieldTypeGroup { label: string; types: TypeOption[] }

const opt = (type: DataTableFieldType): TypeOption => ({ type, label: friendlyTypeName(type), icon: typeGlyph(type) });

// Names and glyphs come from data/fieldTypeLabels (plain words, never raw Frappe types).
const DATA_GROUPS: FieldTypeGroup[] = [
	{ label: 'Text', types: [opt('Data'), opt('Text')] },
	{ label: 'Numbers', types: [opt('Int'), opt('Float'), opt('Currency'), opt('Percent')] },
	{ label: 'Date & time', types: [opt('Date'), opt('Datetime'), opt('Time'), opt('Duration')] },
	{ label: 'Choice', types: [opt('Select'), opt('Check'), opt('Rating')] },
	{ label: 'Reference', types: [opt('Link')] },
	{ label: 'Other', types: [opt('Color'), opt('Phone')] },
	{ label: 'Media', types: [opt('Attach'), opt('Attach Image')] },
];

const LAYOUT_GROUP: FieldTypeGroup = {
	label: 'Layout',
	types: [
		{ type: 'Tab Break', label: 'Tab', icon: Folder },
		{ type: 'Section Break', label: 'Section', icon: Minus },
		{ type: 'Column Break', label: 'Column', icon: Columns },
	],
};

interface FieldTypeSelectorProps {
	onSelect: (type: DataTableFieldType) => void;
	trigger: React.ReactNode;
	value?: DataTableFieldType;
	/** Hide layout elements (when changing the type of an existing field). */
	dataOnly?: boolean;
}

export function FieldTypeSelector({ onSelect, trigger, value, dataOnly }: FieldTypeSelectorProps) {
	const [open, setOpen] = useState(false);
	const [query, setQuery] = useState('');
	const groups = dataOnly ? DATA_GROUPS : [...DATA_GROUPS, LAYOUT_GROUP];

	const handleSelect = (type: DataTableFieldType) => {
		setOpen(false);
		onSelect(type);
	};

	const q = query.trim().toLowerCase();
	const filteredGroups = q
		? groups
				.map((g) => ({ ...g, types: g.types.filter((t) => t.label.toLowerCase().includes(q)) }))
				.filter((g) => g.types.length > 0)
		: groups;

	return (
		<Popover open={open} onOpenChange={setOpen}>
			<PopoverTrigger asChild>{trigger}</PopoverTrigger>
			<PopoverContent className="w-80 p-0 rounded-lg border border-line bg-panel" align="center" side="top" collisionPadding={16}>
				<div className="sticky top-0 z-10 bg-panel border-b border-line p-3 space-y-2">
					<h4 className="font-medium text-sm">Choose field type</h4>
					<Input
						size="sm"
						value={query}
						onChange={(e) => setQuery(e.target.value)}
						placeholder="Search field types"
						aria-label="Search field types"
					/>
				</div>
				<div className="p-3 max-h-96 overflow-y-auto space-y-4">
					{filteredGroups.map((group) => (
						<div key={group.label}>
							<p className="text-xs font-medium text-steel mb-2">{group.label}</p>
							<div className="grid grid-cols-2 gap-1">
								{group.types.map((ft) => {
									const Icon = ft.icon;
									const isSelected = ft.type === value;
									return (
										<Button
											key={ft.type}
											variant="ghost"
											size="sm"
											aria-pressed={isSelected}
											className={`justify-start gap-2 font-normal ${isSelected ? 'border border-signal bg-signal/5' : ''}`}
											onClick={() => handleSelect(ft.type)}
										>
											<Icon className="w-4 h-4 text-steel shrink-0" />
											{ft.label}
										</Button>
									);
								})}
							</div>
						</div>
					))}
				</div>
			</PopoverContent>
		</Popover>
	);
}
