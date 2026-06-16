import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { UIComponentRendererProps } from '../registry';

interface StatsCardData {
	title: string;
	value: number | string;
	change?: number;
	changeLabel?: string;
	format?: 'number' | 'currency' | 'percent' | 'compact';
	prefix?: string;
	suffix?: string;
	description?: string;
}

function formatValue(value: number | string, format?: string, prefix?: string, suffix?: string): string {
	if (typeof value === 'string') return `${prefix ?? ''}${value}${suffix ?? ''}`;
	const p = prefix ?? '';
	const s = suffix ?? '';
	switch (format) {
		case 'currency':
			return `${p}${new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(value)}${s}`;
		case 'percent':
			return `${p}${value.toFixed(1)}%${s}`;
		case 'compact':
			return `${p}${new Intl.NumberFormat('en-US', { notation: 'compact' }).format(value)}${s}`;
		default:
			return `${p}${new Intl.NumberFormat().format(value)}${s}`;
	}
}

export function StatsCardRenderer({ component }: UIComponentRendererProps) {
	const d = component.data as StatsCardData | null;
	if (!d?.title) return null;

	const change = d.change ?? 0;
	const isPositive = change > 0;
	const isNeutral = change === 0;

	return (
		<Card className="w-full max-w-xs shrink-0">
			<CardHeader className="pb-2">
				<CardTitle className="text-sm font-medium text-muted-foreground">{d.title}</CardTitle>
			</CardHeader>
			<CardContent className="space-y-1">
				<div className="text-2xl font-bold tracking-tight">
					{formatValue(d.value, d.format, d.prefix, d.suffix)}
				</div>
				{d.change !== undefined && (
					<div className={cn(
						'flex items-center gap-1 text-xs font-medium',
						isNeutral && 'text-muted-foreground',
						isPositive && 'text-emerald-600',
						!isPositive && !isNeutral && 'text-red-600',
					)}>
						{isNeutral
							? <Minus className="size-3" />
							: isPositive
								? <TrendingUp className="size-3" />
								: <TrendingDown className="size-3" />}
						<span>{isPositive ? '+' : ''}{change.toFixed(1)}%</span>
						{d.changeLabel && <span className="font-normal text-muted-foreground">{d.changeLabel}</span>}
					</div>
				)}
				{d.description && (
					<p className="text-xs text-muted-foreground pt-1">{d.description}</p>
				)}
			</CardContent>
		</Card>
	);
}
