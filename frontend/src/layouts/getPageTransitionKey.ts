/**
 * Key for the page fade-in. Changes on real page changes only, so query-string
 * edits (filters, tabs) don't re-trigger the animation. Chat collapses to one
 * key so switching conversations doesn't fade the whole pane.
 */
export function getPageTransitionKey(pathname: string): string {
	if (pathname.startsWith('/chat')) return '/chat';
	if (pathname.startsWith('/ui/chat')) return '/ui/chat';
	return pathname;
}

/** Stable outlet key for chat routes (keep the listing sidebar mounted). */
export function getOutletRemountKey(pathname: string, search = ''): string {
	const transitionKey = getPageTransitionKey(pathname);
	return transitionKey === pathname ? `${pathname}${search}` : transitionKey;
}
