import { Link } from 'react-router-dom';

import { labels } from '@/components/solutions/labels';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import type { NumberSummary } from '@/types/solutions';

export const TRIAGE_LABEL = 'Triage assistant';

export function RoutingOrderCard({ summary }: { summary: NumberSummary }) {
	const rows = summary.routing_order;
	const byName = new Map(summary.solutions.map((s) => [s.name, s]));
	return (
		<Card>
			<CardHeader className="space-y-1">
				<CardTitle className="text-base">Routing order</CardTitle>
				<CardDescription>The first matching rule answers. Edit rules inside each {labels.solutionLower}.</CardDescription>
			</CardHeader>
			<CardContent>
				<div className="overflow-x-auto">
					<table className="w-full text-sm">
						<thead>
							<tr className="text-left text-xs text-steel">
								<th className="pb-1 pr-3 font-medium">#</th>
								<th className="pb-1 pr-3 font-medium">Rule</th>
								<th className="pb-1 font-medium">Goes to</th>
							</tr>
						</thead>
						<tbody>
							{rows.length === 0 ? (
								<tr>
									<td colSpan={3} className="py-2 text-steel">
										No rules
									</td>
								</tr>
							) : (
								rows.map((r) => {
									const sol = r.solution ? byName.get(r.solution) : undefined;
									return (
										<tr key={`${r.rank}-${r.label}`} className="border-t border-line">
											<td className="py-2 pr-3 font-mono">{r.rank}</td>
											<td className="py-2 pr-3">{r.label}</td>
											<td className="py-2">
												{r.solution ? (
													<span className="flex flex-wrap items-center gap-2">
														<Link className="text-primary underline-offset-2 hover:underline" to={`/solutions/${encodeURIComponent(r.solution)}`}>
															{sol?.title ?? r.solution}
														</Link>
														{sol && sol.status !== 'Live' ? <Badge variant="pill-warning">Paused</Badge> : null}
													</span>
												) : (
													TRIAGE_LABEL
												)}
											</td>
										</tr>
									);
								})
							)}
						</tbody>
					</table>
				</div>
			</CardContent>
		</Card>
	);
}
