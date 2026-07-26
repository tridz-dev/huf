import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import type { UIComponentRendererProps } from '../registry';

interface InfoItem {
	label: string;
	value: string | number;
	badge?: boolean;
}

interface InfoSection {
	heading?: string;
	items: InfoItem[];
}

interface InfoCardData {
	title: string;
	description?: string;
	status?: string;
	items?: InfoItem[];
	sections?: InfoSection[];
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

function renderItems(items: InfoItem[]) {
	return (
		<div className="space-y-2">
			{items.map((item, i) => (
				<div key={i} className="flex items-center justify-between gap-4 text-sm">
					<span className="text-muted-foreground shrink-0">{item.label}</span>
					{item.badge ? (
						<Badge variant={badgeVariant(String(item.value))}>{String(item.value)}</Badge>
					) : (
						<span className="font-medium text-right truncate">{String(item.value)}</span>
					)}
				</div>
			))}
		</div>
	);
}

export function InfoCardRenderer({ component }: UIComponentRendererProps) {
	const d = component.data as InfoCardData | null;
	if (!d?.title) return null;

	return (
		<Card className="w-full max-w-md">
			<CardHeader className="pb-3">
				<div className="flex items-center justify-between gap-3">
					<CardTitle className="text-base">{d.title}</CardTitle>
					{d.status && <Badge variant={badgeVariant(d.status)}>{d.status}</Badge>}
				</div>
				{d.description && <CardDescription>{d.description}</CardDescription>}
			</CardHeader>
			<CardContent className="space-y-4">
				{d.items && renderItems(d.items)}
				{d.sections?.map((section, si) => (
					<div key={si} className="space-y-2">
						{si > 0 && <Separator />}
						{section.heading && (
							<p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground pt-1">
								{section.heading}
							</p>
						)}
						{renderItems(section.items)}
					</div>
				))}
			</CardContent>
		</Card>
	);
}
