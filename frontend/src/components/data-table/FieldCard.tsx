import { GripVertical, X } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import type { DataTableFieldDef } from '@/types/dataTable.types';

interface FieldCardProps {
	field: DataTableFieldDef;
	index: number;
	isSelected: boolean;
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
	onSelect,
	onRemove,
	onDragStart,
	onDragOver,
	onDrop,
}: FieldCardProps) {
	const isLayout = field.fieldtype === 'Section Break' || field.fieldtype === 'Column Break';

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
						? 'border-primary bg-primary/5'
						: 'border-muted-foreground/30 hover:border-muted-foreground/50'
				)}
			>
				<GripVertical className="w-4 h-4 text-muted-foreground cursor-grab shrink-0" />
				<div className="flex items-center gap-2 flex-1 min-w-0">
					{field.fieldtype === 'Section Break' ? (
						<>
							<span className="text-xs text-muted-foreground">---</span>
							<span className="text-sm text-muted-foreground">
								{field.label || 'Section Break'}
							</span>
							<span className="text-xs text-muted-foreground">---</span>
						</>
					) : (
						<>
							<span className="text-xs text-muted-foreground">|</span>
							<span className="text-sm text-muted-foreground">
								{field.label || 'Column Break'}
							</span>
						</>
					)}
				</div>
				<Button
					variant="ghost"
					size="icon"
					className="h-6 w-6 opacity-0 group-hover:opacity-100"
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
					? 'border-primary bg-primary/5 shadow-sm'
					: 'border-border hover:border-muted-foreground/50'
			)}
		>
			<GripVertical className="w-4 h-4 text-muted-foreground cursor-grab shrink-0" />
			<div className="flex-1 min-w-0">
				<div className="flex items-center gap-2">
					<span className="text-sm font-medium truncate">{field.label || 'Untitled'}</span>
					{field.reqd === 1 && (
						<span className="text-destructive text-xs">*</span>
					)}
				</div>
				<div className="flex items-center gap-2 mt-0.5">
					<Badge variant="secondary" className="text-[10px] px-1.5 py-0 h-4">
						{field.fieldtype}
					</Badge>
					<span className="text-[10px] text-muted-foreground">{field.fieldname}</span>
				</div>
			</div>
			<Button
				variant="ghost"
				size="icon"
				className="h-6 w-6 opacity-0 group-hover:opacity-100 shrink-0"
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
