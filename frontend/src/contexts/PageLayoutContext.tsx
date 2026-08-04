import {
	createContext,
	useCallback,
	useContext,
	useMemo,
	useState,
	type ReactNode,
} from 'react';
import type { BreadcrumbItem } from '@/layouts/UnifiedLayout';

export interface PageLayoutConfig {
	hideHeader?: boolean;
	headerActions?: ReactNode;
	breadcrumbs?: BreadcrumbItem[];
}

interface PageLayoutContextValue {
	config: PageLayoutConfig;
	setConfig: (config: PageLayoutConfig) => void;
	/**
	 * The header's action container. Pages portal into it via
	 * `<PageHeaderActions>` when their buttons need page-level context — a
	 * portal keeps the buttons in the page's React tree (so its providers are
	 * in scope) while placing the DOM in the header.
	 */
	headerActionsSlot: HTMLElement | null;
	setHeaderActionsSlot: (element: HTMLElement | null) => void;
}

const PageLayoutContext = createContext<PageLayoutContextValue | null>(null);

export function PageLayoutProvider({ children }: { children: ReactNode }) {
	const [config, setConfigState] = useState<PageLayoutConfig>({});
	const [headerActionsSlot, setHeaderActionsSlot] = useState<HTMLElement | null>(null);

	const setConfig = useCallback((next: PageLayoutConfig) => {
		setConfigState(next);
	}, []);

	const value = useMemo(
		() => ({ config, setConfig, headerActionsSlot, setHeaderActionsSlot }),
		[config, setConfig, headerActionsSlot],
	);

	return (
		<PageLayoutContext.Provider value={value}>
			{children}
		</PageLayoutContext.Provider>
	);
}

export function usePageLayoutContext() {
	const ctx = useContext(PageLayoutContext);
	if (!ctx) {
		throw new Error('usePageLayoutContext must be used within PageLayoutProvider');
	}
	return ctx;
}

/** Non-throwing variant, for chrome that may render outside the app shell. */
export function usePageLayoutContextOptional() {
	return useContext(PageLayoutContext);
}
