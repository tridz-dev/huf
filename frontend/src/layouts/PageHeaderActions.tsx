import type { ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { usePageLayoutContextOptional } from '@/contexts/PageLayoutContext';

/**
 * Render header actions from inside the page.
 *
 * `usePageLayout({ headerActions })` hands a ReactNode to the shell, which
 * renders it in `UnifiedHeader` — outside the page and therefore outside any
 * provider the page sets up. Buttons that call `useAiProviders`, `useModels` or
 * `useFlowContext` crash there. This portals instead: the element stays a child
 * of the page in the React tree (contexts intact) while its DOM lands in the
 * header.
 *
 * Use this whenever the action needs page-level context; the plain
 * `headerActions` config is fine for self-contained buttons.
 */
export function PageHeaderActions({ children }: { children: ReactNode }) {
	const ctx = usePageLayoutContextOptional();
	const slot = ctx?.headerActionsSlot;

	// Null on the first paint (the slot ref lands during the header's commit)
	// and whenever the route hides the header entirely.
	if (!slot) return null;

	return createPortal(children, slot);
}
