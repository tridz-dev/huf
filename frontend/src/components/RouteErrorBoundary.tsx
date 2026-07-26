import { useEffect } from 'react';
import { useRouteError } from 'react-router-dom';
import { Button } from '@/components/ui/button';

const RELOAD_FLAG = 'huf:chunk-reload';

/** True for stale-chunk errors after a frontend redeploy (old tab, new hashes). */
function isChunkLoadError(error: unknown): boolean {
	const message = String((error as { message?: string })?.message || error || '');
	return /dynamically imported module|Loading chunk|Loading CSS chunk|Failed to fetch/i.test(message);
}

/**
 * Route errorElement. Dynamic-import failures mean the browser holds a stale
 * bundle (a new build replaced the hashed chunks) — the only fix is a reload,
 * so do it once automatically and show a calm message instead of the raw
 * "Unexpected Application Error" screen. The flag is cleared on healthy load
 * (AppShell) so future real redeploys reload again.
 */
export function RouteErrorBoundary() {
	const error = useRouteError();
	const chunkError = isChunkLoadError(error);
	const alreadyRetried =
		typeof sessionStorage !== 'undefined' && sessionStorage.getItem(RELOAD_FLAG) === '1';

	useEffect(() => {
		if (!chunkError || alreadyRetried) return;
		sessionStorage.setItem(RELOAD_FLAG, '1');
		window.location.reload();
	}, [chunkError, alreadyRetried]);

	if (chunkError) {
		return (
			<div className="min-h-screen flex flex-col items-center justify-center gap-3 bg-paper text-center px-6">
				<p className="text-sm text-ink font-medium">
					{alreadyRetried ? 'A new version is available.' : 'Updating to the latest version…'}
				</p>
				{alreadyRetried && (
					<>
						<p className="text-xs text-steel max-w-sm">
							The app was updated in the background. Refresh once to load the latest version.
						</p>
						<Button size="sm" onClick={() => window.location.reload()}>
							Refresh
						</Button>
					</>
				)}
			</div>
		);
	}

	return (
		<div className="min-h-screen flex flex-col items-center justify-center gap-3 bg-paper text-center px-6">
			<p className="text-sm text-ink font-medium">Something went wrong.</p>
			<p className="text-xs text-steel max-w-md break-words">
				{(error as { message?: string })?.message || 'Unexpected error'}
			</p>
			<Button size="sm" variant="outline" onClick={() => window.location.assign('/huf')}>
				Back to Hub
			</Button>
		</div>
	);
}

/** Clear the reload guard once the app has loaded healthy. Call from AppShell. */
export function clearChunkReloadFlag() {
	try {
		sessionStorage.removeItem(RELOAD_FLAG);
	} catch {
		/* sessionStorage unavailable */
	}
}
