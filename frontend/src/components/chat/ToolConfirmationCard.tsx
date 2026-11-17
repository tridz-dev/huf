import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import {
	Confirmation,
	ConfirmationTitle,
	ConfirmationRequest,
	ConfirmationAccepted,
	ConfirmationRejected,
	ConfirmationActions,
	ConfirmationAction,
} from '@/components/ai-elements/confirmation';
import type { ExtendedToolState } from '@/components/ai-elements/types';
import {
	decideConfirmation,
	parseExpiresAt,
	confirmationErrorMessage,
	getConfirmationErrorCode,
	type ToolConfirmation,
} from '@/services/toolConfirmationApi';

function formatCountdown(ms: number): string {
	const total = Math.max(0, Math.floor(ms / 1000));
	const m = Math.floor(total / 60);
	const s = total % 60;
	return `${m}:${String(s).padStart(2, '0')}`;
}

const STATE_LABEL: Record<string, string> = {
	approved: 'Sending…',
	executed: 'Approved and sent',
	denied: 'Denied',
	expired: 'Expired',
	failed: 'Approved but failed to run',
};

export interface ToolConfirmationCardProps {
	confirmation: ToolConfirmation;
	/** Called with the server-returned confirmation after a decision, or when an error shows the real state. */
	onUpdated?: (confirmation: ToolConfirmation) => void;
	/** Called after a successful decision so the caller can refresh the follow-up message. */
	onDecided?: (confirmation: ToolConfirmation) => void;
	/** Test seam. */
	now?: () => number;
}

export function ToolConfirmationCard({ confirmation, onUpdated, onDecided, now = Date.now }: ToolConfirmationCardProps) {
	const [busy, setBusy] = useState(false);
	const [tick, setTick] = useState(() => now());
	const expiry = parseExpiresAt(confirmation.expires_at);
	const isPending = confirmation.state === 'pending';
	const locallyExpired = isPending && expiry !== null && tick >= expiry;
	const state = locallyExpired ? 'expired' : confirmation.state;
	const actionable = state === 'pending' && !busy;

	useEffect(() => {
		if (!isPending || expiry === null) return;
		const id = setInterval(() => setTick(now()), 1000);
		return () => clearInterval(id);
	}, [isPending, expiry, now]);

	const toolState: ExtendedToolState = state === 'pending' ? 'approval-requested' : 'approval-responded';
	const approved = state === 'approved' || state === 'executed' || state === 'failed';
	const { summary } = confirmation;

	const decide = async (approve: boolean) => {
		if (!actionable) return;
		setBusy(true);
		try {
			const { confirmation: updated } = await decideConfirmation(confirmation.id, approve);
			onUpdated?.(updated);
			onDecided?.(updated);
			if (updated.state === 'failed') toast.error('The approved action failed to run.');
			else toast.success(approve ? 'Approved.' : 'Denied.');
		} catch (error) {
			const code = getConfirmationErrorCode(error);
			toast.error(confirmationErrorMessage(error));
			// The request is no longer pending server-side: lock the card.
			if (code === 'expired') onUpdated?.({ ...confirmation, state: 'expired' });
			else if (code === 'already_decided') onUpdated?.({ ...confirmation, state: 'approved' });
			else if (code === 'args_changed' || code === 'role_denied' || code === 'not_found') {
				onUpdated?.({ ...confirmation, state: 'denied' });
			} else if (code === 'execution_failed') onUpdated?.({ ...confirmation, state: 'failed' });
		} finally {
			setBusy(false);
		}
	};

	return (
		<Confirmation
			data-testid="tool-confirmation-card"
			data-state={state}
			approval={state === 'pending' ? { id: confirmation.id } : { id: confirmation.id, approved }}
			state={toolState}
			className="w-full max-w-chat-measure"
		>
			<ConfirmationTitle className="flex flex-col gap-1 text-[13px]">
				<span className="font-medium">{summary.action ?? 'Approval needed'}</span>
				<dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-[12px]">
					{summary.recipient_count !== null && (<><dt className="text-steel">Recipients</dt><dd>{summary.recipient_count}</dd></>)}
					{summary.template && (<><dt className="text-steel">Template</dt><dd>{summary.template}</dd></>)}
					{summary.channel && (<><dt className="text-steel">Channel</dt><dd>{summary.channel}</dd></>)}
					{summary.sample && (<><dt className="text-steel">Sample</dt><dd className="whitespace-pre-wrap">{summary.sample}</dd></>)}
				</dl>
				{state === 'pending' && expiry !== null && (
					<span className="text-[12px] text-steel" data-testid="confirmation-countdown">
						Expires in {formatCountdown(expiry - tick)}
					</span>
				)}
				{state !== 'pending' && (
					<span className="text-[12px] text-steel" data-testid="confirmation-state">{STATE_LABEL[state] ?? state}</span>
				)}
			</ConfirmationTitle>
			<ConfirmationRequest>
				<ConfirmationActions>
					<ConfirmationAction variant="outline" disabled={!actionable} onClick={() => decide(false)}>Deny</ConfirmationAction>
					<ConfirmationAction disabled={!actionable} onClick={() => decide(true)}>Approve</ConfirmationAction>
				</ConfirmationActions>
			</ConfirmationRequest>
			<ConfirmationAccepted><span className="sr-only">Approved</span></ConfirmationAccepted>
			<ConfirmationRejected><span className="sr-only">Not approved</span></ConfirmationRejected>
		</Confirmation>
	);
}
