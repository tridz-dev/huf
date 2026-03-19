import {
	BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import type { UIComponentRendererProps } from '../registry';

const COLORS = ['#8884d8', '#82ca9d', '#ffc658', '#ff7300', '#00C49F', '#FF8042', '#0088FE'];

interface BarChartData {
	title?: string;
	description?: string;
	items: Record<string, unknown>[];
	bars?: { dataKey: string; label?: string; color?: string }[];
	dataKey?: string;
	categoryKey?: string;
	stacked?: boolean;
	horizontal?: boolean;
}

export function BarChartRenderer({ component }: UIComponentRendererProps) {
	const d = component.data as BarChartData | null;
	if (!d?.items?.length) return null;

	const catKey = d.categoryKey ?? 'name';
	const bars = d.bars ?? (d.dataKey ? [{ dataKey: d.dataKey }] : inferBars(d.items, catKey));

	return (
		<Card className="w-full">
			{(d.title || d.description) && (
				<CardHeader className="pb-2">
					{d.title && <CardTitle className="text-base">{d.title}</CardTitle>}
					{d.description && <CardDescription>{d.description}</CardDescription>}
				</CardHeader>
			)}
			<CardContent className="pt-4">
				<ResponsiveContainer width="100%" height={300}>
					<BarChart
						data={d.items}
						layout={d.horizontal ? 'vertical' : 'horizontal'}
						margin={{ top: 5, right: 20, left: 10, bottom: 5 }}
					>
						<CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
						{d.horizontal ? (
							<>
								<YAxis dataKey={catKey} type="category" tick={{ fontSize: 12 }} width={80} />
								<XAxis type="number" tick={{ fontSize: 12 }} />
							</>
						) : (
							<>
								<XAxis dataKey={catKey} tick={{ fontSize: 12 }} />
								<YAxis tick={{ fontSize: 12 }} />
							</>
						)}
						<Tooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} />
						{bars.length > 1 && <Legend wrapperStyle={{ fontSize: 12 }} />}
						{bars.map((bar, i) => (
							<Bar
								key={bar.dataKey}
								dataKey={bar.dataKey}
								name={bar.label ?? bar.dataKey}
								fill={bar.color ?? COLORS[i % COLORS.length]}
								radius={[4, 4, 0, 0]}
								stackId={d.stacked ? 'stack' : undefined}
							/>
						))}
					</BarChart>
				</ResponsiveContainer>
			</CardContent>
		</Card>
	);
}

function inferBars(items: Record<string, unknown>[], categoryKey: string) {
	if (!items.length) return [];
	return Object.keys(items[0])
		.filter((k) => k !== categoryKey && typeof items[0][k] === 'number')
		.map((k) => ({ dataKey: k }));
}
