import {
	AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import type { UIComponentRendererProps } from '../registry';

const COLORS = ['#8884d8', '#82ca9d', '#ffc658', '#ff7300', '#00C49F', '#FF8042', '#0088FE'];

interface AreaChartData {
	title?: string;
	description?: string;
	items: Record<string, unknown>[];
	areas?: { dataKey: string; label?: string; color?: string }[];
	xKey?: string;
	stacked?: boolean;
}

export function AreaChartRenderer({ component }: UIComponentRendererProps) {
	const d = component.data as AreaChartData | null;
	if (!d?.items?.length) return null;

	const xKey = d.xKey ?? 'name';
	const areas = d.areas ?? inferAreas(d.items, xKey);

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
					<AreaChart data={d.items} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
						<CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
						<XAxis dataKey={xKey} tick={{ fontSize: 12 }} />
						<YAxis tick={{ fontSize: 12 }} />
						<Tooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} />
						{areas.length > 1 && <Legend wrapperStyle={{ fontSize: 12 }} />}
						{areas.map((area, i) => {
							const color = area.color ?? COLORS[i % COLORS.length];
							return (
								<Area
									key={area.dataKey}
									type="monotone"
									dataKey={area.dataKey}
									name={area.label ?? area.dataKey}
									stroke={color}
									fill={color}
									fillOpacity={0.15}
									strokeWidth={2}
									stackId={d.stacked ? 'stack' : undefined}
								/>
							);
						})}
					</AreaChart>
				</ResponsiveContainer>
			</CardContent>
		</Card>
	);
}

function inferAreas(items: Record<string, unknown>[], xKey: string) {
	if (!items.length) return [];
	return Object.keys(items[0])
		.filter((k) => k !== xKey && typeof items[0][k] === 'number')
		.map((k) => ({ dataKey: k }));
}
