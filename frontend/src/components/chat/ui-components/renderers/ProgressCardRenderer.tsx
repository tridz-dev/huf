import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { cn } from '@/lib/utils';
import type { UIComponentRendererProps } from '../registry';

interface ProgressItem {
	label: string;
	value: number;
	max?: number;
	color?: string;
}

interface ProgressCardData {
	title?: string;
	description?: string;
	items?: ProgressItem[];
	value?: number;
	max?: number;
	label?: string;
	showPercent?: boolean;
}

function pct(value: number, max: number): number {
	return Math.min(100, Math.max(0, (value / max) * 100));
}

export function ProgressCardRenderer({ component }: UIComponentRendererProps) {
	const d = component.data as ProgressCardData | null;
	if (!d) return null;

	// Single progress bar mode
	if (d.value !== undefined && !d.items) {
		const max = d.max ?? 100;
		const percent = pct(d.value, max);
		return (
			<Card className="w-full max-w-sm">
				{(d.title || d.description) && (
					<CardHeader className="pb-3">
						{d.title && <CardTitle className="text-base">{d.title}</CardTitle>}
						{d.description && <CardDescription>{d.description}</CardDescription>}
					</CardHeader>
				)}
				<CardContent className={cn(!d.title && !d.description && 'pt-6', 'space-y-2')}>
					<div className="flex items-center justify-between text-sm">
						<span className="text-muted-foreground">{d.label ?? 'Progress'}</span>
						<span className="font-medium">
							{d.showPercent !== false ? `${percent.toFixed(0)}%` : `${new Intl.NumberFormat().format(d.value)} / ${new Intl.NumberFormat().format(max)}`}
						</span>
					</div>
					<Progress value={percent} className="h-2" />
				</CardContent>
			</Card>
		);
	}

	// Multi-progress mode
	if (!d.items?.length) return null;

	return (
		<Card className="w-full">
			{(d.title || d.description) && (
				<CardHeader className="pb-3">
					{d.title && <CardTitle className="text-base">{d.title}</CardTitle>}
					{d.description && <CardDescription>{d.description}</CardDescription>}
				</CardHeader>
			)}
			<CardContent className={cn(!d.title && !d.description && 'pt-6', 'space-y-4')}>
				{d.items.map((item, i) => {
					const max = item.max ?? 100;
					const percent = pct(item.value, max);
					return (
						<div key={i} className="space-y-1.5">
							<div className="flex items-center justify-between text-sm">
								<span className="text-muted-foreground">{item.label}</span>
								<span className="font-medium">{percent.toFixed(0)}%</span>
							</div>
							<Progress value={percent} className="h-2" />
						</div>
					);
				})}
			</CardContent>
		</Card>
	);
}
