import { useCallback, useEffect, useMemo, useState } from 'react';
import {
	AppWindow,
	CircleHelp,
	ExternalLink,
	MoreVertical,
	Power,
	TriangleAlert,
} from 'lucide-react';
import { toast } from 'sonner';
import { PageFrame } from '@/layouts/PageFrame';
import { GridView, BaseCard, FilterBar, EmptyState } from '../components/dashboard';
import { ExperimentalBadge } from '../components/common/ExperimentalBadge';
import { CardHeader, CardTitle, CardDescription, CardAction } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogHeader,
	DialogTitle,
} from '@/components/ui/dialog';
import {
	DropdownMenu,
	DropdownMenuContent,
	DropdownMenuItem,
	DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { cn } from '@/lib/utils';
import { getHufApps, setHufAppEnabled } from '../services/appsApi';
import type { HufApp } from '@/types/hufApp.types';

export { AppsPage };
export default AppsPage;

/**
 * Search + category filters only appear once the launcher holds enough
 * apps to be worth filtering.
 */
const FILTER_THRESHOLD = 8;

/** Known HUF App categories; chips also pick up custom ones from data. */
const DEFAULT_CATEGORIES = [
	'Create',
	'Plan',
	'Research',
	'Automate',
	'Analyze',
	'Communicate',
	'Manage',
	'Other',
];

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

function CategoryChip({
	label,
	active,
	onClick,
}: {
	label: string;
	active: boolean;
	onClick: () => void;
}) {
	return (
		<Button
			type="button"
			variant="outline"
			onClick={onClick}
			className={cn(
				'h-auto items-center px-2 py-1 font-mono text-[10.5px] uppercase tracking-wide',
				active
					? 'border-ink text-ink'
					: 'border-line bg-paper-deep text-steel hover:text-ink'
			)}
		>
			{label}
		</Button>
	);
}

function AppCard({
	app,
	onToggleEnabled,
}: {
	app: HufApp;
	onToggleEnabled: (app: HufApp) => void;
}) {
	// `enabled` is only present for System Managers; its presence doubles
	// as the signal to offer the admin enable/disable action.
	const canAdminister = typeof app.enabled === 'number';
	const isDisabled = app.enabled === 0;
	const route = isDisabled ? null : appRoute(app);

	// The whole card is a real anchor: left-click navigates (full page
	// load), cmd/ctrl/middle-click opens a new tab natively. Disabled apps
	// never get the anchor — the card is inert and can't be opened.
	const card = (
		<BaseCard
			className={cn(
				'flex flex-col',
				isDisabled ? 'opacity-60' : 'cursor-pointer hover:border-ink'
			)}
		>
			<CardHeader className="pb-3">
				<CardTitle className="line-clamp-1 flex items-center gap-2 text-body-text font-semibold">
					<AppIcon app={app} />
					{app.title}
				</CardTitle>
				<CardDescription className="text-steel text-ui-text line-clamp-2 min-h-[2.5rem]">
					{app.description || 'No description'}
				</CardDescription>
				<CardAction className="top-5 flex items-center gap-1">
					{isDisabled && (
						<Badge variant="secondary" size="sm">
							Disabled
						</Badge>
					)}
					{app.category && (
						<Badge variant="secondary" size="sm">
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
					{canAdminister && (
						<DropdownMenu>
							<DropdownMenuTrigger asChild>
								<Button
									variant="ghost"
									size="icon"
									className="h-7 w-7 text-steel-soft hover:text-ink"
									title="App actions"
									onClick={(e) => {
										e.stopPropagation();
										e.preventDefault();
									}}
								>
									<MoreVertical className="w-3.5 h-3.5" />
								</Button>
							</DropdownMenuTrigger>
							<DropdownMenuContent
								align="end"
								onClick={(e) => {
									e.stopPropagation();
									e.preventDefault();
								}}
							>
								<DropdownMenuItem
									onClick={(e) => {
										e.stopPropagation();
										e.preventDefault();
										onToggleEnabled(app);
									}}
								>
									<Power className="w-3.5 h-3.5" />
									{isDisabled ? 'Enable app' : 'Disable app'}
								</DropdownMenuItem>
							</DropdownMenuContent>
						</DropdownMenu>
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

function AppsHelpDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
	return (
		<Dialog open={open} onOpenChange={onOpenChange}>
			<DialogContent>
				<DialogHeader>
					<DialogTitle>About HUF apps</DialogTitle>
					<DialogDescription>
						What shows up here, and why.
					</DialogDescription>
				</DialogHeader>
				<div className="space-y-4 text-sm font-body text-steel">
					<section className="space-y-1">
						<h3 className="font-semibold text-ink">What is a HUF App?</h3>
						<p>
							A HUF App is an independently installed Frappe app that registers
							itself with HUF. Each one gets a card here so you can launch its
							own frontend.
						</p>
					</section>
					<section className="space-y-1">
						<h3 className="font-semibold text-ink">Where do apps come from?</h3>
						<p>
							Apps are installed server-side with bench and discovered
							automatically once they register. Nothing is ever installed from
							this screen — it's a launcher, not an installer.
						</p>
					</section>
					<section className="space-y-1">
						<h3 className="font-semibold text-ink">Why is the list filtered?</h3>
						<p>
							You only see apps you're allowed to open. Apps an administrator
							has disabled are hidden entirely.
						</p>
					</section>
					<section className="space-y-1">
						<h3 className="font-semibold text-ink">What does HUF give them?</h3>
						<p>
							Registered apps build on HUF's agents, runs, knowledge, and tools,
							so they share the same automation backbone as the rest of your
							workspace.
						</p>
					</section>
				</div>
			</DialogContent>
		</Dialog>
	);
}

function AppsPage() {
	const [apps, setApps] = useState<HufApp[]>([]);
	const [loading, setLoading] = useState(true);
	const [error, setError] = useState<string | null>(null);
	const [helpOpen, setHelpOpen] = useState(false);
	const [search, setSearch] = useState('');
	const [category, setCategory] = useState<string>('All');

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

	const handleToggleEnabled = useCallback(
		async (app: HufApp) => {
			const enabling = app.enabled === 0;
			try {
				await setHufAppEnabled(app.app_id, enabling);
				toast.success(`${app.title} ${enabling ? 'enabled' : 'disabled'}`);
				await load();
			} catch (err: any) {
				toast.error(`Failed to update ${app.title}`, {
					description: err?.message,
				});
			}
		},
		[load]
	);

	// Chip set: the known categories plus any custom ones present in data.
	const categories = useMemo(() => {
		const seen = new Set(DEFAULT_CATEGORIES.map((c) => c.toLowerCase()));
		const custom: string[] = [];
		for (const app of apps) {
			const cat = app.category?.trim();
			if (cat && !seen.has(cat.toLowerCase())) {
				seen.add(cat.toLowerCase());
				custom.push(cat);
			}
		}
		return [...DEFAULT_CATEGORIES, ...custom];
	}, [apps]);

	const showFilters = apps.length >= FILTER_THRESHOLD;

	const visibleApps = useMemo(() => {
		if (!showFilters) return apps;
		const query = search.trim().toLowerCase();
		return apps.filter((app) => {
			if (category !== 'All' && (app.category || 'Other') !== category) return false;
			if (!query) return true;
			return (
				app.title.toLowerCase().includes(query) ||
				(app.description || '').toLowerCase().includes(query)
			);
		});
	}, [apps, showFilters, search, category]);

	return (
		<PageFrame
			title="Apps"
			badge={<ExperimentalBadge />}
			actions={
				<Button
					variant="ghost"
					size="icon"
					className="h-9 w-9 text-steel-soft hover:text-ink"
					title="About HUF apps"
					onClick={() => setHelpOpen(true)}
				>
					<CircleHelp className="w-5 h-5" />
				</Button>
			}
			filters={
				showFilters ? (
					<FilterBar
						searchPlaceholder="Search apps..."
						searchValue={search}
						onSearchChange={setSearch}
						actions={
							<div className="flex flex-wrap items-center gap-1.5">
								<CategoryChip
									label="All"
									active={category === 'All'}
									onClick={() => setCategory('All')}
								/>
								{categories.map((cat) => (
									<CategoryChip
										key={cat}
										label={cat}
										active={category === cat}
										onClick={() => setCategory(cat)}
									/>
								))}
							</div>
						}
					/>
				) : undefined
			}
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
					items={visibleApps}
					columns={{ sm: 1, md: 2, lg: 3 }}
					loading={loading}
					emptyState={
						apps.length > 0 ? (
							<EmptyState
								variant="no-results"
								icon={AppWindow}
								title="No apps found"
								filterTerm={search}
								secondaryAction={{
									label: 'Clear filters',
									onClick: () => {
										setSearch('');
										setCategory('All');
									},
								}}
							/>
						) : (
							<EmptyState
								variant="passive"
								icon={AppWindow}
								title="No apps available yet"
								description="Installed apps that depend on HUF will appear here."
							/>
						)
					}
					renderItem={(app) => <AppCard app={app} onToggleEnabled={handleToggleEnabled} />}
					keyExtractor={(app) => app.app_id}
				/>
			)}
			<AppsHelpDialog open={helpOpen} onOpenChange={setHelpOpen} />
		</PageFrame>
	);
}
