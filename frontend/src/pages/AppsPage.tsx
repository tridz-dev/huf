import { useCallback, useEffect, useState } from 'react';
import { AppWindow, ExternalLink, TriangleAlert } from 'lucide-react';
import { PageLayout, GridView, BaseCard } from '../components/dashboard';
import { CardHeader, CardTitle, CardDescription, CardAction } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { getHufApps } from '../services/appsApi';
import type { HufApp } from '@/types/hufApp.types';

export { AppsPage };
export default AppsPage;

/**
 * Resolve the launch URL for a registered HUF App. Apps are independent
 * Frappe apps with their own frontends, so cards are plain anchors doing
 * full-page site-local navigation — never an iframe, never SPA router
 * navigation.
 *
 * Defensive: manifests are validated server-side, but never link to
 * anything that isn't a plain site-local path.
 */
function appRoute(app: HufApp): string | null {
	const route = app.route;
	if (typeof route !== 'string' || !route.startsWith('/') || route.startsWith('//')) {
		return null;
	}
	return route;
}

function AppIcon({ app }: { app: HufApp }) {
	const [iconFailed, setIconFailed] = useState(false);
	// Icons are site-local asset paths (e.g. /assets/huf_workspace/icon.svg).
	// Anything else — missing, malformed, or failed to load — falls back to
	// the generic app icon.
	const iconSrc =
		typeof app.icon === 'string' && app.icon.startsWith('/') && !app.icon.startsWith('//')
			? app.icon
			: null;

	if (!iconSrc || iconFailed) {
		return <AppWindow className="w-5 h-5 shrink-0 text-steel-soft" />;
	}

	return (
		<img
			src={iconSrc}
			alt=""
			className="w-5 h-5 shrink-0 object-contain"
			onError={() => setIconFailed(true)}
		/>
	);
}

function AppCard({ app }: { app: HufApp }) {
	const route = appRoute(app);

	// The whole card is a real anchor: left-click navigates (full page
	// load), cmd/ctrl/middle-click opens a new tab natively.
	const card = (
		<BaseCard className="flex flex-col cursor-pointer hover:border-ink">
			<CardHeader className="pb-3">
				<CardTitle className="font-body font-semibold text-[15px] line-clamp-1 flex items-center gap-2">
					<AppIcon app={app} />
					{app.title}
				</CardTitle>
				<CardDescription className="text-steel text-[13px] line-clamp-2 min-h-[2.5rem]">
					{app.description || 'No description'}
				</CardDescription>
				<CardAction className="top-5 flex items-center gap-1">
					{app.category && (
						<Badge variant="secondary" className="text-xs">
							{app.category}
						</Badge>
					)}
					{route && (
						<Button
							variant="ghost"
							size="icon"
							className="h-7 w-7 text-steel-soft hover:text-ink"
							title="Open in new tab"
							onClick={(e) => {
								// Don't let the click reach the wrapping anchor.
								e.stopPropagation();
								e.preventDefault();
								window.open(route, '_blank', 'noopener');
							}}
						>
							<ExternalLink className="w-3.5 h-3.5" />
						</Button>
					)}
				</CardAction>
			</CardHeader>
		</BaseCard>
	);

	if (!route) {
		return card;
	}
	return (
		<a href={route} className="block h-full text-inherit no-underline">
			{card}
		</a>
	);
}

function AppsPage() {
	const [apps, setApps] = useState<HufApp[]>([]);
	const [loading, setLoading] = useState(true);
	const [error, setError] = useState<string | null>(null);

	const load = useCallback(async () => {
		setLoading(true);
		setError(null);
		try {
			setApps(await getHufApps());
		} catch (err: any) {
			setError(err?.message || 'An error occurred while loading apps.');
		} finally {
			setLoading(false);
		}
	}, []);

	useEffect(() => {
		load();
	}, [load]);

	return (
		<PageLayout
			title="Apps"
			subtitle="Launch applications built on HUF"
		>
			{error ? (
				<div className="flex flex-col items-center justify-center py-12 text-center">
					<TriangleAlert className="w-12 h-12 text-steel-soft mb-4" />
					<p className="font-body text-steel-soft mb-2">Couldn't load apps</p>
					<p className="text-sm text-steel mb-4">{error}</p>
					<Button variant="outline" onClick={load}>
						Retry
					</Button>
				</div>
			) : (
				<GridView
					items={apps}
					columns={{ sm: 1, md: 2, lg: 3 }}
					loading={loading}
					emptyState={
						<div className="text-center py-12">
							<AppWindow className="w-12 h-12 text-steel-soft mx-auto mb-4" />
							<p className="font-body text-steel-soft mb-2">No apps available yet</p>
							<p className="text-sm text-steel">
								Installed apps that depend on HUF will appear here.
							</p>
						</div>
					}
					renderItem={(app) => <AppCard app={app} />}
					keyExtractor={(app) => app.app_id}
				/>
			)}
		</PageLayout>
	);
}
