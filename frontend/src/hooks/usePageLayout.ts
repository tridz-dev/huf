import { useEffect } from 'react';
import { usePageLayoutContext, type PageLayoutConfig } from '@/contexts/PageLayoutContext';

/** Set dynamic header/breadcrumb config for the current page; cleared on unmount. */
export function usePageLayout({ hideHeader, headerActions, breadcrumbs }: PageLayoutConfig) {
	const { setConfig } = usePageLayoutContext();
	const breadcrumbsKey = breadcrumbs ? JSON.stringify(breadcrumbs) : '';

	useEffect(() => {
		setConfig({ hideHeader, headerActions, breadcrumbs });
		return () => setConfig({});
	}, [setConfig, hideHeader, headerActions, breadcrumbsKey, breadcrumbs]);
}

export type { PageLayoutConfig } from '@/contexts/PageLayoutContext';
