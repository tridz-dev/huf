import { useState } from 'react';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
	AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
	AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { TimeStamp } from '@/components/whatsapp/TimeStamp';
import { decideJoinRequest, type JoinRequest } from '@/services/telegramGroupsApi';

type Decision = 'approve' | 'decline';

/** People waiting to join groups the bot manages, with approve / decline behind a confirm. */
export function JoinQueue({ gateway, items, onChanged }: { gateway: string; items: JoinRequest[]; onChanged: () => void }) {
	const [pending, setPending] = useState<{ item: JoinRequest; decision: Decision } | null>(null);
	const [busy, setBusy] = useState(false);

	const confirm = async () => {
		if (!pending) return;
		setBusy(true);
		const res = await decideJoinRequest(gateway, pending.item.entry, pending.decision);
		setBusy(false);
		setPending(null);
		if (res.ok) toast.success(pending.decision === 'approve' ? 'Request approved' : 'Request declined');
		else toast.error(res.error);
		onChanged();
	};

	if (items.length === 0) {
		return <p className="rounded-sm border border-line p-6 text-center text-xs text-steel">No one is waiting to join. Requests to join your groups will show up here.</p>;
	}
	const who = (i: JoinRequest) => i.user_name || `User ${i.user_id}`;
	const where = (i: JoinRequest) => i.chat_title || `Group ${i.chat_id}`;

	return (
		<div className="space-y-2">
			<ul className="divide-y divide-line rounded-sm border border-line">
				{items.map((i) => (
					<li key={i.entry} className="flex flex-wrap items-center justify-between gap-2 p-3 text-xs">
						<div>
							<div className="text-ink">{who(i)} wants to join <span className="font-medium">{where(i)}</span></div>
							<div className="text-steel">
								Asked <TimeStamp value={i.requested_at} />
								{i.expires_at && <> · {i.expired ? <Badge variant="pill-danger">Expired</Badge> : <>expires <TimeStamp value={i.expires_at} /></>}</>}
							</div>
						</div>
						<div className="space-x-2">
							<Button size="sm" disabled={i.expired} onClick={() => setPending({ item: i, decision: 'approve' })}>Approve</Button>
							<Button size="sm" variant="outline" disabled={i.expired} onClick={() => setPending({ item: i, decision: 'decline' })}>Decline</Button>
						</div>
					</li>
				))}
			</ul>
			<AlertDialog open={pending !== null} onOpenChange={(o) => !o && !busy && setPending(null)}>
				<AlertDialogContent>
					<AlertDialogHeader>
						<AlertDialogTitle>{pending?.decision === 'approve' ? 'Approve this request?' : 'Decline this request?'}</AlertDialogTitle>
						<AlertDialogDescription>
							{pending && (pending.decision === 'approve'
								? `${who(pending.item)} will be let into ${where(pending.item)}.`
								: `${who(pending.item)} will be turned away from ${where(pending.item)}. They can ask again.`)}
						</AlertDialogDescription>
					</AlertDialogHeader>
					<AlertDialogFooter>
						<AlertDialogCancel disabled={busy}>Cancel</AlertDialogCancel>
						<AlertDialogAction disabled={busy} onClick={(e) => { e.preventDefault(); void confirm(); }}>
							{pending?.decision === 'approve' ? 'Approve' : 'Decline'}
						</AlertDialogAction>
					</AlertDialogFooter>
				</AlertDialogContent>
			</AlertDialog>
		</div>
	);
}
