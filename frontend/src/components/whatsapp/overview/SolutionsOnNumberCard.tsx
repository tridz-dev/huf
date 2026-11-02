import { Info } from 'lucide-react';
import { Link } from 'react-router-dom';

import { labels } from '@/components/solutions/labels';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import type { NumberSummary } from '@/types/solutions';

export interface SolutionsOnNumberCardProps {
	gateway: string;
	summary: NumberSummary;
}

export const NO_SOLUTION_TITLE = 'This number replies to no one yet.';

export function SolutionsOnNumberCard({ gateway, summary }: SolutionsOnNumberCardProps) {
	const list = summary.solutions;
	const live = list.filter((s) => s.status === 'Live');
	return (
		<Card>
			<CardHeader className="flex flex-row items-start justify-between gap-3 space-y-0">
				<div className="space-y-1">
					<CardTitle className="text-base">{labels.solutions} on this number</CardTitle>
					<CardDescription>Daily limit used, by {labels.solutionLower}.</CardDescription>
				</div>
				<Button asChild size="sm" variant="outline">
					<Link to={`/solutions/new?gateway=${encodeURIComponent(gateway)}`}>Add {labels.solutionLower}</Link>
				</Button>
			</CardHeader>
			<CardContent className="space-y-3">
				{list.length > 0 ? (
					<ul className="divide-y divide-line">
						{list.map((s) => (
							<li key={s.name} className="flex flex-wrap items-center gap-3 py-2">
								<span className="min-w-0 flex-1 truncate text-sm font-medium text-ink">{s.title}</span>
								<Badge variant={s.status === 'Live' ? 'pill-success' : 'pill-warning'}>{s.status}</Badge>
								<div className="w-32 text-xs text-steel">
									{s.usage_pct == null ? (
										<span>n/a</span>
									) : (
										<div className="flex items-center gap-2">
											<div
												role="meter"
												aria-label={`${s.title} daily limit used`}
												aria-valuemin={0}
												aria-valuemax={100}
												aria-valuenow={Math.round(s.usage_pct)}
												className="h-1.5 flex-1 overflow-hidden rounded-full bg-paper-deep"
											>
												<div className="h-full bg-primary" style={{ width: `${Math.min(100, Math.max(0, s.usage_pct))}%` }} />
											</div>
											<span className="font-mono">{Math.round(s.usage_pct)}%</span>
										</div>
									)}
								</div>
								<Link className="text-sm text-primary underline-offset-2 hover:underline" to={`/solutions/${encodeURIComponent(s.name)}`}>
									Open<span className="sr-only"> {s.title}</span>
								</Link>
							</li>
						))}
					</ul>
				) : null}
				{live.length === 0 ? (
					<div className="flex items-start gap-2 rounded-md bg-paper-deep p-3 text-sm text-ink" role="status">
						<Info className="mt-0.5 h-4 w-4 shrink-0 text-steel" aria-hidden />
						<span>
							<b>{NO_SOLUTION_TITLE}</b> Every {labels.solutionLower} on it is paused, or none exists.
						</span>
					</div>
				) : null}
				{list.length > 1 ? (
					<p className="text-xs text-steel">
						{list.length} {labels.solutionsLower} share this number's quality rating and daily limit.
					</p>
				) : null}
			</CardContent>
		</Card>
	);
}
