import { Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { FieldCard } from './FieldCard';
import { FieldTypeSelector } from './FieldTypeSelector';
import type { DataTableFieldDef, DataTableFieldType } from '@/types/dataTable.types';

interface TableBuilderCanvasProps {
	fields: DataTableFieldDef[];
	selectedFieldIndex: number | null;
	onSelectField: (index: number | null) => void;
	onAddField: (type: DataTableFieldType) => void;
	onRemoveField: (index: number) => void;
	onReorderFields: (from: number, to: number) => void;
}

export function TableBuilderCanvas({
	fields,
	selectedFieldIndex,
	onSelectField,
	onAddField,
	onRemoveField,
	onReorderFields,
}: TableBuilderCanvasProps) {
	const handleDragStart = (e: React.DragEvent, index: number) => {
		e.dataTransfer.setData('text/plain', index.toString());
		e.dataTransfer.effectAllowed = 'move';
	};

	const handleDragOver = (e: React.DragEvent, _index: number) => {
		e.preventDefault();
		e.dataTransfer.dropEffect = 'move';
	};

	const handleDrop = (e: React.DragEvent, toIndex: number) => {
		e.preventDefault();
		const fromIndex = parseInt(e.dataTransfer.getData('text/plain'), 10);
		if (fromIndex !== toIndex) {
			onReorderFields(fromIndex, toIndex);
		}
	};

	return (
		<div className="space-y-2">
			{fields.length === 0 ? (
				<div className="flex flex-col items-center justify-center py-12 border border-dashed rounded-lg">
					<p className="text-sm text-muted-foreground mb-4">
						No fields yet. Add your first field to get started.
					</p>
					<FieldTypeSelector
						onSelect={onAddField}
						trigger={
							<Button variant="outline" size="sm">
								<Plus className="w-4 h-4 mr-2" />
								Add Field
							</Button>
						}
					/>
				</div>
			) : (
				<>
					{fields.map((field, index) => (
						<FieldCard
							key={`${field.fieldname}-${index}`}
							field={field}
							index={index}
							isSelected={selectedFieldIndex === index}
							onSelect={() =>
								onSelectField(selectedFieldIndex === index ? null : index)
							}
							onRemove={() => onRemoveField(index)}
							onDragStart={handleDragStart}
							onDragOver={handleDragOver}
							onDrop={handleDrop}
						/>
					))}
					<FieldTypeSelector
						onSelect={onAddField}
						trigger={
							<Button variant="outline" size="sm" className="w-full">
								<Plus className="w-4 h-4 mr-2" />
								Add Field
							</Button>
						}
					/>
				</>
			)}
		</div>
	);
}
