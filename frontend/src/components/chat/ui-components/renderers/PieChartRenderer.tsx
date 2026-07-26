import {
	PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer,
} from 'recharts';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import type { UIComponentRendererProps } from '../registry';

const COLORS = ['#8884d8', '#82ca9d', '#ffc658', '#ff7300', '#00C49F', '#FF8042', '#0088FE', '#FFBB28'];

interface PieChartData {
	title?: string;
	description?: string;
	items: Record<string, unknown>[];
	nameKey?: string;
	valueKey?: string;
	donut?: boolean;
	colors?: string[];
}

export function PieChartRenderer({ component }: UIComponentRendererProps) {
	const d = component.data as PieChartData | null;
	if (!d?.items?.length) return null;

	const nameKey = d.nameKey ?? 'name';
	const valueKey = d.valueKey ?? 'value';
	const colors = d.colors ?? COLORS;
	const innerRadius = d.donut ? 60 : 0;

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
					<PieChart>
						<Pie
							data={d.items}
							dataKey={valueKey}
							nameKey={nameKey}
							cx="50%"
							cy="50%"
							innerRadius={innerRadius}
							outerRadius={100}
							paddingAngle={2}
							label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
							labelLine={{ strokeWidth: 1 }}
						>
							{d.items.map((_, i) => (
								<Cell key={i} fill={colors[i % colors.length]} />
							))}
						</Pie>
						<Tooltip
							formatter={(value: number) => new Intl.NumberFormat().format(value)}
							contentStyle={{ fontSize: 12, borderRadius: 8 }}
						/>
						<Legend wrapperStyle={{ fontSize: 12 }} />
					</PieChart>
				</ResponsiveContainer>
			</CardContent>
		</Card>
	);
}
