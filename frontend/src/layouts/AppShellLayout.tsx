import { Outlet, useLocation, useMatches } from 'react-router-dom';
import { AnimatePresence, motion } from 'motion/react';
import { UnifiedLayout } from '@/layouts/UnifiedLayout';
import { getPageTransitionKey } from '@/layouts/getPageTransitionKey';
import { PageLayoutProvider, usePageLayoutContext, type PageLayoutConfig } from '@/contexts/PageLayoutContext';

export interface AppShellRouteHandle extends PageLayoutConfig {}

function AppShellLayoutInner() {
	const location = useLocation();
	const matches = useMatches();
	const { config } = usePageLayoutContext();

	const routeHandle = matches
		.map((match) => match.handle as AppShellRouteHandle | undefined)
		.filter(Boolean)
		.pop();

	const hideHeaderFromPath =
		location.pathname.startsWith('/chat') ||
		location.pathname === '/' ||
		location.pathname.startsWith('/playground');

	const hideHeader = config.hideHeader ?? routeHandle?.hideHeader ?? hideHeaderFromPath;
	const headerActions = config.headerActions ?? routeHandle?.headerActions;
	const breadcrumbs = config.breadcrumbs ?? routeHandle?.breadcrumbs;

	return (
		<UnifiedLayout
			hideHeader={hideHeader}
			headerActions={headerActions}
			breadcrumbs={breadcrumbs}
		>
			<AnimatePresence mode="wait" initial={false}>
				<motion.div
					key={getPageTransitionKey(location.pathname)}
					initial={{ opacity: 0 }}
					animate={{ opacity: 1 }}
					exit={{ opacity: 0 }}
					transition={{ duration: 0.15 }}
					className="flex h-full min-h-0 flex-col"
				>
					<Outlet />
				</motion.div>
			</AnimatePresence>
		</UnifiedLayout>
	);
}

export function AppShellLayout() {
	return (
		<PageLayoutProvider>
			<AppShellLayoutInner />
		</PageLayoutProvider>
	);
}
