import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Table2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { getExposedAppTables } from '@/services/appsApi';
import type { ExposedAppTable } from '@/services/appsApi';

/**
 * Frappe desk list route for a DocType: lowercase, spaces → hyphens
 * (e.g. "Sales Invoice" → /app/sales-invoice).
 */
function deskRoute(doctype: string): string {
	return `/app/${doctype.trim().toLowerCase().replace(/\s+/g, '-')}`;
}

/**
 * "App Tables" section for the bottom of the Data page: DocTypes exposed
 * by installed HUF Apps, each linking to its Frappe desk list. Renders
 * nothing when no app exposes tables (or the fetch fails — the section
 * is supplementary, never worth an error state).
 */
export function AppTablesSection() {
	const [rows, setRows] = useState<ExposedAppTable[]>([]);

	useEffect(() => {
		let cancelled = false;
		getExposedAppTables()
			.then((tables) => {
				if (!cancelled) setRows(tables);
			})
			.catch(() => {
				// Stay hidden on error.
			});
		return () => {
			cancelled = true;
		};
	}, []);

	if (rows.length === 0) return null;

	return (
		<section className="mt-8 border-t border-line pt-6 space-y-3">
			<div className="space-y-1">
				<h2 className="font-display font-bold text-[16px] text-ink">
					App tables
				</h2>
				<p className="text-sm font-body text-steel">
					Tables exposed by installed HUF Apps.
				</p>
			</div>
			<div className="border border-line divide-y divide-line">
				{rows.map((row) => (
					<div
						key={`${row.app_id}:${row.doctype}`}
						className="flex items-center justify-between gap-4 px-4 py-2.5"
					>
						<div className="flex items-center gap-3 min-w-0">
							<Table2 className="w-4 h-4 shrink-0 text-steel-soft" />
							<Link
								to={deskRoute(row.doctype)}
								className="font-body text-[14px] text-ink hover:underline truncate"
							>
								{row.doctype}
							</Link>
						</div>
						<Badge variant="secondary" className="shrink-0">
							{row.app_title}
						</Badge>
					</div>
				))}
			</div>
		</section>
	);
}
