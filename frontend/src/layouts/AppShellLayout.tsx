import { Suspense, useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { UnifiedLayout } from '@/layouts/UnifiedLayout';
import { ShellRoutes } from '@/layouts/ShellRoutes';
import { getPageTransitionKey } from '@/layouts/getPageTransitionKey';
import { getShellRouteHandle } from '@/layouts/shellRouteHandles';
import { PageLayoutProvider, usePageLayoutContext, type PageLayoutConfig } from '@/contexts/PageLayoutContext';
import { PageLoader } from '@/components/PageLoader';

export interface AppShellRouteHandle extends PageLayoutConfig {}

function AppShellLayoutInner() {
	const location = useLocation();
	const { config, setConfig } = usePageLayoutContext();

	useEffect(() => {
		setConfig({});
	}, [location.pathname, location.search, setConfig]);

	const routeHandle = getShellRouteHandle(location.pathname);

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
			<Suspense fallback={<PageLoader />}>
				{/*
					Fade only the content area — the sidebar and header stay mounted,
					unlike the old app-wide AnimatePresence. Pure CSS, so it adds no
					render work to navigation.
				*/}
				<div
					key={getPageTransitionKey(location.pathname)}
					className="flex flex-1 min-h-0 flex-col animate-in fade-in duration-200 motion-reduce:animate-none"
				>
					<ShellRoutes />
				</div>
			</Suspense>
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
