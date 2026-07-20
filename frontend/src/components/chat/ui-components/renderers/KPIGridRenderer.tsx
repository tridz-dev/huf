import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { UIComponentRendererProps } from '../registry';

interface KPIItem {
	label: string;
	value: number | string;
	change?: number;
	format?: 'number' | 'currency' | 'percent' | 'compact';
	prefix?: string;
	suffix?: string;
}

interface KPIGridData {
	title?: string;
	items: KPIItem[];
	columns?: number;
}

function fmtValue(v: number | string, format?: string, prefix?: string, suffix?: string): string {
	if (typeof v === 'string') return `${prefix ?? ''}${v}${suffix ?? ''}`;
	const p = prefix ?? '';
	const s = suffix ?? '';
	switch (format) {
		case 'currency':
			return `${p}${new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(v)}${s}`;
		case 'percent':
			return `${p}${v.toFixed(1)}%${s}`;
		case 'compact':
			return `${p}${new Intl.NumberFormat('en-US', { notation: 'compact' }).format(v)}${s}`;
		default:
			return `${p}${new Intl.NumberFormat().format(v)}${s}`;
	}
}

export function KPIGridRenderer({ component }: UIComponentRendererProps) {
	const d = component.data as KPIGridData | null;
	if (!d?.items?.length) return null;

	const cols = d.columns ?? Math.min(d.items.length, 4);
	const gridClass = cols <= 2 ? 'grid-cols-2' : cols === 3 ? 'grid-cols-3' : 'grid-cols-4';

	return (
		<Card className="w-full">
			{d.title && (
				<CardHeader className="pb-3">
					<CardTitle className="text-base">{d.title}</CardTitle>
				</CardHeader>
			)}
			<CardContent className={cn(!d.title && 'pt-6')}>
				<div className={cn('grid gap-4', gridClass)}>
					{d.items.map((item, i) => {
						const change = item.change ?? 0;
						const isPos = change > 0;
						const isZero = change === 0;
						return (
							<div key={i} className="space-y-1">
								<p className="text-xs font-medium text-muted-foreground">{item.label}</p>
								<p className="text-xl font-bold tracking-tight">
									{fmtValue(item.value, item.format, item.prefix, item.suffix)}
								</p>
								{item.change !== undefined && (
									<div className={cn(
										'flex items-center gap-1 text-xs',
										isZero && 'text-muted-foreground',
										isPos && 'text-emerald-600',
										!isPos && !isZero && 'text-red-600',
									)}>
										{isZero
											? <Minus className="size-3" />
											: isPos
												? <TrendingUp className="size-3" />
												: <TrendingDown className="size-3" />}
										<span>{isPos ? '+' : ''}{change.toFixed(1)}%</span>
									</div>
								)}
							</div>
						);
					})}
				</div>
			</CardContent>
		</Card>
	);
}
