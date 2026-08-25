import { ChevronDown, Mic, MicOff, Phone, PhoneOff } from "lucide-react";
import { useEffect, useRef } from "react";
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "../ui/dialog";
import { Button } from "../ui/button";
import { cn } from "@/lib/utils";
import type { UseVoiceCallResult } from "@/hooks/useVoiceCall";

interface VoiceCallOverlayProps {
    voiceCall: UseVoiceCallResult;
    agentName: string;
    /** Ends the call — same handler the compact bar wires to `voiceCall.stop`. */
    onEndCall: () => void;
    /** Restarts a call after an error/end state — same handler as the compact bar. */
    onStartCall: () => void;
    /** Collapses this overlay back to the compact bar. Does NOT end the call. */
    onMinimize: () => void;
}

/**
 * Full-viewport "in call" takeover, shown while a voice call is connecting
 * or live — mirrors the elevated call UI in ChatGPT Advanced Voice Mode /
 * Claude voice mode. This is purely a view on top of useVoiceCall's state
 * machine: minimizing swaps back to the compact bar in ChatInput.tsx
 * without touching the call itself.
 *
 * Reuses the same Dialog/Portal primitives as every other full-screen
 * surface in this codebase (see components/modals/*) rather than inventing
 * a bespoke `fixed inset-0` overlay.
 */
export function VoiceCallOverlay({ voiceCall, agentName, onEndCall, onStartCall, onMinimize }: VoiceCallOverlayProps) {
    const transcriptRef = useRef<HTMLDivElement>(null);

    // Auto-scroll the caption list to the newest turn as the transcript grows.
    useEffect(() => {
        const el = transcriptRef.current;
        if (el) {
            el.scrollTop = el.scrollHeight;
        }
    }, [voiceCall.transcript]);

    const statusLabel =
        voiceCall.status === 'connecting'
            ? 'Connecting…'
            : voiceCall.status === 'live'
                ? (voiceCall.isMuted ? 'Muted' : 'Live')
                : voiceCall.status === 'error'
                    ? (voiceCall.error || 'Call error')
                    : 'Call ended';

    return (
        <Dialog open onOpenChange={(open) => { if (!open) onMinimize(); }}>
            <DialogContent
                className="flex flex-col items-center justify-center gap-8 !rounded-none border-0 bg-background p-8 sm:!rounded-none sm:max-w-[100vw] sm:h-[100dvh] sm:translate-x-0 sm:translate-y-0 sm:left-0 sm:top-0"
                onEscapeKeyDown={(event) => {
                    // Escape minimizes the overlay — it must never end a live call.
                    event.preventDefault();
                    onMinimize();
                }}
                onInteractOutside={(event) => event.preventDefault()}
            >
                <DialogTitle className="sr-only">Voice call with {agentName}</DialogTitle>
                <DialogDescription className="sr-only">{statusLabel}</DialogDescription>

                <button
                    type="button"
                    onClick={onMinimize}
                    className="absolute left-4 top-4 flex size-9 items-center justify-center rounded-full text-steel hover:bg-panel hover:text-ink"
                    aria-label="Minimize call"
                    title="Minimize call"
                >
                    <ChevronDown className="size-5" />
                </button>

                {/* Orb: same visual language as the compact bar's orb in
                    ChatInput.tsx, scaled up for a dedicated takeover view. */}
                <span className="relative flex size-36 shrink-0 items-center justify-center">
                    {voiceCall.status === 'live' && !voiceCall.isMuted && (
                        <span className="absolute inset-0 rounded-full bg-destructive/40 animate-ping motion-reduce:animate-none" />
                    )}
                    <span
                        className={cn(
                            "relative rounded-full transition-all duration-300 ease-out",
                            voiceCall.status === 'live' && !voiceCall.isMuted && "size-32 bg-destructive shadow-xl",
                            voiceCall.status === 'live' && voiceCall.isMuted && "size-24 bg-steel-soft opacity-70",
                            voiceCall.status === 'connecting' && "size-24 bg-steel-soft animate-pulse motion-reduce:animate-none",
                            (voiceCall.status === 'error' || voiceCall.status === 'ended') && "size-20 bg-steel-soft"
                        )}
                    />
                </span>

                <div className="flex flex-col items-center gap-2 text-center">
                    <span className="text-lg font-medium text-ink">{agentName}</span>
                    <span className="text-sm text-steel">{statusLabel}</span>
                </div>

                {voiceCall.transcript.length > 0 && (
                    <div
                        ref={transcriptRef}
                        className="flex w-full max-w-md flex-col gap-2 overflow-y-auto px-2 text-sm"
                        style={{ maxHeight: '30vh' }}
                        aria-live="polite"
                    >
                        {voiceCall.transcript.map((turn) => (
                            <p
                                key={turn.id}
                                className={cn(
                                    "leading-snug",
                                    turn.role === 'agent' ? "text-ink" : "text-steel",
                                    !turn.final && "opacity-70",
                                )}
                            >
                                <span className="font-medium">{turn.role === 'agent' ? agentName : 'You'}: </span>
                                {turn.text}
                            </p>
                        ))}
                    </div>
                )}

                <div className="flex items-center gap-6">
                    {voiceCall.status === 'live' && (
                        <button
                            type="button"
                            onClick={voiceCall.isMuted ? voiceCall.unmute : voiceCall.mute}
                            className="flex size-16 items-center justify-center rounded-full border border-input bg-panel text-ink hover:bg-panel/80"
                            aria-label={voiceCall.isMuted ? "Unmute microphone" : "Mute microphone"}
                            title={voiceCall.isMuted ? "Unmute microphone" : "Mute microphone"}
                        >
                            {voiceCall.isMuted ? <MicOff className="size-6" /> : <Mic className="size-6" />}
                        </button>
                    )}
                    {(voiceCall.status === 'live' || voiceCall.status === 'connecting') && (
                        <Button
                            type="button"
                            onClick={onEndCall}
                            className="flex !size-16 items-center justify-center !rounded-full bg-destructive p-0 text-destructive-foreground hover:bg-destructive/90"
                            aria-label="End call"
                            title="End call"
                        >
                            <PhoneOff className="size-6" />
                        </Button>
                    )}
                    {(voiceCall.status === 'error' || voiceCall.status === 'ended') && (
                        <Button
                            type="button"
                            onClick={onStartCall}
                            className="flex !size-16 items-center justify-center !rounded-full bg-ink p-0 text-white hover:bg-ink/90"
                            aria-label="Talk to this agent"
                            title="Talk to this agent"
                        >
                            <Phone className="size-6" />
                        </Button>
                    )}
                </div>
            </DialogContent>
        </Dialog>
    );
}
