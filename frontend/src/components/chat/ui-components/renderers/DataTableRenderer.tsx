import {
	Table, TableHeader, TableBody, TableRow, TableHead, TableCell, TableCaption,
} from '@/components/ui/table';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import type { UIComponentRendererProps } from '../registry';

interface DataTableData {
	title?: string;
	description?: string;
	columns: (string | { label: string; align?: 'left' | 'center' | 'right'; format?: 'currency' | 'number' | 'percent' | 'badge' })[];
	rows: (string | number | null)[][];
	caption?: string;
	striped?: boolean;
}

function resolveColumn(col: DataTableData['columns'][number]) {
	if (typeof col === 'string') return { label: col, align: 'left' as const, format: undefined };
	return { label: col.label, align: col.align ?? 'left', format: col.format };
}

function formatCell(value: string | number | null, format?: string): React.ReactNode {
	if (value === null || value === undefined) return '—';

	if (format === 'badge') {
		const str = String(value);
		const variant = badgeVariant(str);
		return <Badge variant={variant}>{str}</Badge>;
	}

	if (typeof value === 'number') {
		switch (format) {
			case 'currency':
				return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(value);
			case 'percent':
				return `${value.toFixed(1)}%`;
			case 'number':
				return new Intl.NumberFormat().format(value);
			default:
				return new Intl.NumberFormat().format(value);
		}
	}

	return String(value);
}

function badgeVariant(text: string): 'default' | 'secondary' | 'destructive' | 'outline' {
	const lower = text.toLowerCase();
	if (['paid', 'completed', 'active', 'approved', 'submitted', 'success'].some((w) => lower.includes(w)))
		return 'default';
	if (['overdue', 'failed', 'cancelled', 'rejected', 'error'].some((w) => lower.includes(w)))
		return 'destructive';
	if (['pending', 'draft', 'unpaid', 'open'].some((w) => lower.includes(w)))
		return 'secondary';
	return 'outline';
}

export function DataTableRenderer({ component }: UIComponentRendererProps) {
	const d = component.data as DataTableData | null;
	if (!d?.columns?.length || !d?.rows?.length) return null;

	const cols = d.columns.map(resolveColumn);

	return (
		<Card className="w-full overflow-hidden">
			{(d.title || d.description) && (
				<CardHeader className="pb-2">
					{d.title && <CardTitle className="text-base">{d.title}</CardTitle>}
					{d.description && <CardDescription>{d.description}</CardDescription>}
				</CardHeader>
			)}
			<CardContent className={cn(!d.title && !d.description && 'pt-0', 'px-0 pb-0')}>
				<div className="overflow-x-auto">
					<Table>
						{d.caption && <TableCaption>{d.caption}</TableCaption>}
						<TableHeader>
							<TableRow>
								{cols.map((col, i) => (
									<TableHead key={i} className={cn(col.align === 'right' && 'text-right', col.align === 'center' && 'text-center')}>
										{col.label}
									</TableHead>
								))}
							</TableRow>
						</TableHeader>
						<TableBody>
							{d.rows.map((row, ri) => (
								<TableRow key={ri} className={cn(d.striped && ri % 2 === 1 && 'bg-muted/40')}>
									{row.map((cell, ci) => {
										const col = cols[ci];
										return (
											<TableCell
												key={ci}
												className={cn(
													col?.align === 'right' && 'text-right',
													col?.align === 'center' && 'text-center',
												)}
											>
												{formatCell(cell, col?.format)}
											</TableCell>
										);
									})}
								</TableRow>
							))}
						</TableBody>
					</Table>
				</div>
			</CardContent>
		</Card>
	);
}
