import {
	LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import type { UIComponentRendererProps } from '../registry';

const COLORS = ['#8884d8', '#82ca9d', '#ffc658', '#ff7300', '#00C49F', '#FF8042', '#0088FE'];

interface LineChartData {
	title?: string;
	description?: string;
	items: Record<string, unknown>[];
	lines?: { dataKey: string; label?: string; color?: string; dashed?: boolean }[];
	xKey?: string;
	curved?: boolean;
}

export function LineChartRenderer({ component }: UIComponentRendererProps) {
	const d = component.data as LineChartData | null;
	if (!d?.items?.length) return null;

	const xKey = d.xKey ?? 'name';
	const lines = d.lines ?? inferLines(d.items, xKey);
	const curve = d.curved !== false ? 'monotone' : 'linear';

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
					<LineChart data={d.items} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
						<CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
						<XAxis dataKey={xKey} tick={{ fontSize: 12 }} />
						<YAxis tick={{ fontSize: 12 }} />
						<Tooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} />
						{lines.length > 1 && <Legend wrapperStyle={{ fontSize: 12 }} />}
						{lines.map((line, i) => (
							<Line
								key={line.dataKey}
								type={curve}
								dataKey={line.dataKey}
								name={line.label ?? line.dataKey}
								stroke={line.color ?? COLORS[i % COLORS.length]}
								strokeWidth={2}
								strokeDasharray={line.dashed ? '5 5' : undefined}
								dot={{ r: 3 }}
								activeDot={{ r: 5 }}
							/>
						))}
					</LineChart>
				</ResponsiveContainer>
			</CardContent>
		</Card>
	);
}

function inferLines(items: Record<string, unknown>[], xKey: string) {
	if (!items.length) return [];
	return Object.keys(items[0])
		.filter((k) => k !== xKey && typeof items[0][k] === 'number')
		.map((k) => ({ dataKey: k }));
}
