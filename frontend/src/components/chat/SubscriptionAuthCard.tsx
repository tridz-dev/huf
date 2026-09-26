import { useEffect, useRef, useState } from 'react';
import { ExternalLink, KeyRound, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
    beginSubscriptionAuth,
    cancelSubscriptionAuth,
    pollSubscriptionAuth,
    submitSubscriptionAuthInput,
    type SubscriptionAuthChallenge,
} from '@/services/subscriptionRuntimeApi';

const POLL_INTERVAL_MS = 4000;

interface SubscriptionAuthCardProps {
    /** Subscription Runtime this challenge belongs to. `begin_subscription_auth`
     * is keyed by runtime name and resumes any already-active challenge, so
     * this is the only identifier the backend auth-challenge API needs. */
    runtimeName?: string;
    /** Backend-supplied reason text for why authentication is required
     * (e.g. `auth_reason` from the `subscription_auth_required` realtime
     * event), shown until the full challenge details load. */
    authReason?: string;
    /** Called once polling/manual-check detects the runtime is authenticated
     * again, so the caller can swap this card for a normal "resuming..." state. */
    onResumed?: () => void;
    /** Called after the user cancels the in-flight challenge. */
    onCancelled?: () => void;
}

/**
 * Inline, recoverable "waiting on authentication" card for a parked agent run
 * (PLAN.md §64.2). This is a normal waiting state, not an error — never style
 * it like `ChatErrorCard`. Never renders a password input: at most a single
 * text field for a provider-generated, one-time paste-back value handled by
 * `submitSubscriptionAuthInput`.
 */
export function SubscriptionAuthCard({ runtimeName, authReason, onResumed, onCancelled }: SubscriptionAuthCardProps) {
    const [challenge, setChallenge] = useState<SubscriptionAuthChallenge | null>(null);
    const [loading, setLoading] = useState(false);
    const [checking, setChecking] = useState(false);
    const [cancelling, setCancelling] = useState(false);
    const [resumed, setResumed] = useState(false);
    const [codeValue, setCodeValue] = useState('');
    const [submittingCode, setSubmittingCode] = useState(false);
    const [loadError, setLoadError] = useState<string | null>(null);
    const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const cancelledRef = useRef(false);

    // A device/browser challenge is something the provider's own page detects
    // completion of on its own, so HUF can auto-poll for it. A terminal/manual
    // flow instead waits on a one-time value the user pastes back, which
    // `submitSubscriptionAuthInput` (not polling) resolves — the
    // `SubscriptionAuthChallenge` shape has no explicit `poll_supported` flag,
    // so this is inferred from `mode`.
    const pollSupported = challenge?.mode === 'browser' || challenge?.mode === 'device_code';
    const acceptsPastedCode = challenge?.mode === 'terminal_code' || challenge?.mode === 'manual_command';

    const clearPollTimer = () => {
        if (pollTimerRef.current) {
            clearTimeout(pollTimerRef.current);
            pollTimerRef.current = null;
        }
    };

    useEffect(() => {
        cancelledRef.current = false;
        return () => {
            cancelledRef.current = true;
            clearPollTimer();
        };
    }, []);

    useEffect(() => {
        if (!runtimeName) return;
        let active = true;
        setLoading(true);
        setLoadError(null);
        beginSubscriptionAuth(runtimeName)
            .then((result) => {
                if (!active) return;
                setChallenge(result);
            })
            .catch(() => {
                if (!active) return;
                setLoadError("Couldn't load the sign-in details for this runtime.");
            })
            .finally(() => {
                if (active) setLoading(false);
            });
        return () => {
            active = false;
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [runtimeName]);

    const handleTerminalState = (state: string) => {
        if (state === 'ready') {
            setResumed(true);
            clearPollTimer();
            onResumed?.();
        }
    };

    const checkOnce = async () => {
        if (!challenge) return;
        setChecking(true);
        try {
            const status = await pollSubscriptionAuth(challenge.name);
            if (cancelledRef.current) return;
            handleTerminalState(status.state);
        } catch {
            // Swallow: the next scheduled/manual attempt retries.
        } finally {
            if (!cancelledRef.current) setChecking(false);
        }
    };

    // Auto-poll while the card is shown and the runtime detects completion on
    // its own — per PLAN.md §64.2, HUF should never make the user click a
    // button to notice they've finished signing in when polling can do it.
    useEffect(() => {
        if (!challenge || !pollSupported || resumed) return;

        const tick = async () => {
            await checkOnce();
            if (!cancelledRef.current && !resumed) {
                pollTimerRef.current = setTimeout(tick, POLL_INTERVAL_MS);
            }
        };
        pollTimerRef.current = setTimeout(tick, POLL_INTERVAL_MS);
        return () => clearPollTimer();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [challenge?.name, pollSupported, resumed]);

    const handleCancel = async () => {
        if (!challenge) {
            onCancelled?.();
            return;
        }
        setCancelling(true);
        try {
            await cancelSubscriptionAuth(challenge.name);
            onCancelled?.();
        } finally {
            setCancelling(false);
        }
    };

    const handleSubmitCode = async () => {
        if (!challenge || !codeValue.trim()) return;
        setSubmittingCode(true);
        try {
            const status = await submitSubscriptionAuthInput(challenge.name, codeValue.trim());
            handleTerminalState(status.state);
        } finally {
            setSubmittingCode(false);
        }
    };

    if (resumed) {
        return (
            <div className="flex w-full max-w-xl items-center gap-2 rounded-lg border border-line bg-paper-deep px-3 py-2.5 text-[13px] text-steel">
                <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin" />
                <span>Signed in. Resuming this conversation...</span>
            </div>
        );
    }

    return (
        <div className="w-full max-w-xl rounded-lg border border-amber-400/40 bg-amber-400/10 p-3 dark:border-amber-300/30 dark:bg-amber-300/10">
            <div className="flex items-start gap-2">
                <KeyRound className="h-4 w-4 mt-0.5 shrink-0 text-amber-600 dark:text-amber-300" />
                <div className="flex-1 min-w-0 space-y-2.5">
                    <div>
                        <p className="text-sm font-medium text-amber-800 dark:text-amber-200">
                            Authentication required to continue this conversation.
                        </p>
                        {(challenge?.safe_instructions || authReason) && (
                            <p className="mt-0.5 text-sm text-amber-800/90 dark:text-amber-200/80 whitespace-pre-wrap break-words">
                                {challenge?.safe_instructions || authReason}
                            </p>
                        )}
                    </div>

                    {loading && (
                        <div className="flex items-center gap-1.5 text-xs text-amber-800/80 dark:text-amber-200/70">
                            <Loader2 className="h-3 w-3 animate-spin" />
                            Preparing sign-in...
                        </div>
                    )}

                    {loadError && (
                        <p className="text-xs text-amber-800/80 dark:text-amber-200/70">{loadError}</p>
                    )}

                    {challenge?.verification_url && (
                        <a
                            href={challenge.verification_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1.5 text-sm font-medium text-amber-900 underline underline-offset-2 dark:text-amber-100"
                        >
                            Open sign-in page
                            <ExternalLink className="h-3.5 w-3.5" />
                        </a>
                    )}

                    {challenge?.user_code && (
                        <div className="flex items-center gap-2">
                            <span className="text-xs text-amber-800/80 dark:text-amber-200/70">Code</span>
                            <code className="rounded-md border border-amber-400/50 bg-paper px-2.5 py-1 font-mono text-base font-semibold tracking-wider text-amber-900 dark:border-amber-300/40 dark:text-amber-100">
                                {challenge.user_code}
                            </code>
                        </div>
                    )}

                    {acceptsPastedCode && (
                        <div className="flex items-center gap-2">
                            <Input
                                type="text"
                                inputMode="text"
                                autoComplete="off"
                                placeholder="Paste the code shown after signing in"
                                value={codeValue}
                                onChange={(e) => setCodeValue(e.target.value)}
                                className="h-8 max-w-[240px] font-mono text-sm"
                            />
                            <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                className="h-8 text-xs"
                                onClick={handleSubmitCode}
                                disabled={!codeValue.trim() || submittingCode}
                            >
                                {submittingCode && <Loader2 className="h-3 w-3 animate-spin" />}
                                Submit
                            </Button>
                        </div>
                    )}

                    <div className="flex items-center gap-2 pt-0.5">
                        {!pollSupported && (
                            <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                className="h-7 text-xs"
                                onClick={checkOnce}
                                disabled={checking || !challenge}
                            >
                                {checking && <Loader2 className="h-3 w-3 animate-spin" />}
                                I've completed sign-in
                            </Button>
                        )}
                        {pollSupported && (
                            <span className="flex items-center gap-1.5 text-xs text-amber-800/70 dark:text-amber-200/60">
                                <Loader2 className="h-3 w-3 animate-spin" />
                                Waiting for sign-in to complete...
                            </span>
                        )}
                        <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            className="h-7 text-xs text-amber-900/80 hover:text-amber-900 dark:text-amber-100/80"
                            onClick={handleCancel}
                            disabled={cancelling}
                        >
                            {cancelling && <Loader2 className="h-3 w-3 animate-spin" />}
                            Cancel
                        </Button>
                    </div>
                </div>
            </div>
        </div>
    );
}
