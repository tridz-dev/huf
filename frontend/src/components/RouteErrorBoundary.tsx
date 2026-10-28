import { useEffect } from 'react';
import { useRouteError } from 'react-router-dom';
import { Button } from '@/components/ui/button';

const RELOAD_FLAG = 'huf:chunk-reload';
/** One automatic reload per minute: a chunk that is still missing after it must show the Reload screen, not loop. */
const RELOAD_WINDOW_MS = 60_000;

function reloadedRecently(): boolean {
	try {
		const at = Number(sessionStorage.getItem(RELOAD_FLAG));
		return Number.isFinite(at) && at > 0 && Date.now() - at < RELOAD_WINDOW_MS;
	} catch {
		return false;
	}
}

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
	const alreadyRetried = reloadedRecently();

	useEffect(() => {
		if (!chunkError || alreadyRetried) return;
		try {
			sessionStorage.setItem(RELOAD_FLAG, String(Date.now()));
		} catch {
			/* sessionStorage unavailable */
		}
		window.location.reload();
	}, [chunkError, alreadyRetried]);

	if (chunkError) {
		return (
			<div className="min-h-screen flex flex-col items-center justify-center gap-3 bg-paper text-center px-6" data-testid="chunk-error-screen">
				<p className="text-sm text-ink font-medium">
					{alreadyRetried ? 'Something went wrong' : 'Updating to the latest version…'}
				</p>
				{alreadyRetried && (
					<>
						<p className="text-xs text-steel max-w-sm">
							A part of the app could not be loaded, usually because it was updated in the background. Reload to get the latest version.
						</p>
						<Button size="sm" onClick={() => window.location.reload()}>
							Reload
						</Button>
					</>
				)}
			</div>
		);
	}

	return (
		<div className="min-h-screen flex flex-col items-center justify-center gap-3 bg-paper text-center px-6">
			<p className="text-sm text-ink font-medium">Something went wrong</p>
			<p className="text-xs text-steel max-w-md break-words">
				{(error as { message?: string })?.message || 'Unexpected error'}
			</p>
			<Button size="sm" variant="outline" onClick={() => window.location.assign('/huf')}>
				Back to Hub
			</Button>
		</div>
	);
}

/** Forget the reload guard once the app has stayed healthy for a while (not at mount: the page chunk may still fail). */
export function clearChunkReloadFlag() {
	window.setTimeout(() => {
		try {
			sessionStorage.removeItem(RELOAD_FLAG);
		} catch {
			/* sessionStorage unavailable */
		}
	}, RELOAD_WINDOW_MS);
}
