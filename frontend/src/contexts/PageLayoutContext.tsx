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
}

const PageLayoutContext = createContext<PageLayoutContextValue | null>(null);

export function PageLayoutProvider({ children }: { children: ReactNode }) {
	const [config, setConfigState] = useState<PageLayoutConfig>({});

	const setConfig = useCallback((next: PageLayoutConfig) => {
		setConfigState(next);
	}, []);

	const value = useMemo(() => ({ config, setConfig }), [config, setConfig]);

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
