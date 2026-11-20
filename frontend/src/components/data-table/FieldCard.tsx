import { GripVertical, X } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { LAYOUT_FIELD_TYPES } from '@/data/fieldTypes';
import { friendlyTypeName, typeGlyph } from '@/data/fieldTypeLabels';
import type { DataTableFieldDef } from '@/types/dataTable.types';

interface FieldCardProps {
	field: DataTableFieldDef;
	index: number;
	isSelected: boolean;
	/** The field has a problem to fix before saving. */
	hasError?: boolean;
	onSelect: () => void;
	onRemove: () => void;
	onDragStart: (e: React.DragEvent, index: number) => void;
	onDragOver: (e: React.DragEvent, index: number) => void;
	onDrop: (e: React.DragEvent, index: number) => void;
}

export function FieldCard({
	field,
	index,
	isSelected,
	hasError,
	onSelect,
	onRemove,
	onDragStart,
	onDragOver,
	onDrop,
}: FieldCardProps) {
	const isLayout = LAYOUT_FIELD_TYPES.includes(field.fieldtype);
	const TypeIcon = typeGlyph(field.fieldtype);

	if (isLayout) {
		return (
			<div
				draggable
				onDragStart={(e) => onDragStart(e, index)}
				onDragOver={(e) => onDragOver(e, index)}
				onDrop={(e) => onDrop(e, index)}
				onClick={onSelect}
				className={cn(
					'group flex items-center gap-2 px-3 py-2 rounded-md border border-dashed cursor-pointer transition-colors',
					isSelected
						? 'border-line-dark bg-paper-deep'
						: 'border-steel/30 hover:border-steel/50'
				)}
			>
				<GripVertical className="w-4 h-4 text-steel cursor-grab shrink-0" />
				<div className="flex items-center gap-2 flex-1 min-w-0">
					{field.fieldtype === 'Tab Break' ? (
						<>
							<span className="text-xs text-steel">▭</span>
							<span className="text-sm text-steel">
								{field.label || 'Tab Break'}
							</span>
						</>
					) : field.fieldtype === 'Section Break' ? (
						<>
							<span className="text-xs text-steel">---</span>
							<span className="text-sm text-steel">
								{field.label || 'Section Break'}
							</span>
							<span className="text-xs text-steel">---</span>
						</>
					) : (
						<>
							<span className="text-xs text-steel">|</span>
							<span className="text-sm text-steel">
								{field.label || 'Column Break'}
							</span>
						</>
					)}
				</div>
				<Button
					variant="ghost"
					size="icon"
					className="opacity-0 group-hover:opacity-100 focus-visible:opacity-100" aria-label="Remove field"
					onClick={(e) => {
						e.stopPropagation();
						onRemove();
					}}
				>
					<X className="w-3 h-3" />
				</Button>
			</div>
		);
	}

	return (
		<div
			draggable
			onDragStart={(e) => onDragStart(e, index)}
			onDragOver={(e) => onDragOver(e, index)}
			onDrop={(e) => onDrop(e, index)}
			onClick={onSelect}
			className={cn(
				'group flex items-center gap-3 px-3 py-2.5 rounded-md border cursor-pointer transition-colors',
				isSelected
					? 'border-line-dark bg-paper-deep text-ink font-medium '
					: 'border-line hover:border-steel/50'
			)}
		>
			<GripVertical className="w-4 h-4 text-steel cursor-grab shrink-0" />
			<div className="flex-1 min-w-0">
				<div className="flex items-center gap-2">
					<span className={cn('text-sm font-medium truncate', hasError && 'text-destructive')}>{field.label || 'Untitled'}</span>
					{field.reqd === 1 && (
						<span className="text-destructive text-xs">*</span>
					)}
				</div>
				<div className="flex items-center gap-2 mt-0.5">
					<Badge variant="secondary" size="sm" className="gap-1">
						<TypeIcon aria-hidden="true" className="w-3 h-3" />
						{friendlyTypeName(field.fieldtype)}
					</Badge>
					{hasError && <span className="text-micro text-destructive">Needs attention</span>}
				</div>
			</div>
			<Button
				variant="ghost"
				size="icon"
				className="opacity-0 group-hover:opacity-100 focus-visible:opacity-100 shrink-0" aria-label="Remove field"
				onClick={(e) => {
					e.stopPropagation();
					onRemove();
				}}
			>
				<X className="w-3 h-3" />
			</Button>
		</div>
	);
}
