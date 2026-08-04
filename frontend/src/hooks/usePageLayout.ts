import { useEffect, useRef } from 'react';
import { usePageLayoutContext, type PageLayoutConfig } from '@/contexts/PageLayoutContext';

/**
 * Set dynamic header/breadcrumb config for the current page; cleared on unmount.
 *
 * Callers build `breadcrumbs` and `headerActions` inline, so both get a fresh
 * identity on every render. Keeping them in the effect deps made the effect
 * re-run every render, and each `setConfig` publishes a new context value that
 * re-renders the calling page — an unbounded loop that starves React Router's
 * (low-priority) navigation transition, so the URL changes but the page never
 * swaps. Only stable values belong in the deps; the rest is read via a ref.
 *
 * Note: header actions are therefore only re-published when `hideHeader` or the
 * breadcrumbs change. Every caller passes a props-less element, so that is fine
 * today; a page needing state-dependent actions must key them itself.
 */
export function usePageLayout({ hideHeader, headerActions, breadcrumbs }: PageLayoutConfig) {
	const { setConfig } = usePageLayoutContext();
	const breadcrumbsKey = breadcrumbs ? JSON.stringify(breadcrumbs) : '';

	const latest = useRef<PageLayoutConfig>({ hideHeader, headerActions, breadcrumbs });
	latest.current = { hideHeader, headerActions, breadcrumbs };

	useEffect(() => {
		setConfig({ ...latest.current });
		return () => setConfig({});
		// `headerActions`/`breadcrumbs` are deliberately excluded — see above.
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [setConfig, hideHeader, breadcrumbsKey]);
}

export type { PageLayoutConfig } from '@/contexts/PageLayoutContext';
