import { Badge } from '@/components/ui/badge';
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { Skeleton } from '@/components/ui/skeleton';
import { LoadError } from '@/components/whatsapp/BridgeUnavailable';
import { TimeStamp } from '@/components/whatsapp/TimeStamp';
import { KIND_LABEL, statusTone, type TelegramMessageDetail } from '@/services/telegramMessagesApi';

function Field({ label, children }: { label: string; children: React.ReactNode }) {
	return (
		<div className="space-y-0.5">
			<dt className="text-[11px] uppercase tracking-wide text-steel">{label}</dt>
			<dd className="text-xs text-ink">{children}</dd>
		</div>
	);
}

const Empty = () => <span className="text-steel">&mdash;</span>;
const tone = (s: string) => (statusTone(s) === 'good' ? 'pill-success' : statusTone(s) === 'bad' ? 'pill-danger' : 'pill-warning');

export function MessageDetailSheet({
	open, detail, error, onClose,
}: { open: boolean; detail: TelegramMessageDetail | null; error?: string; onClose: () => void }) {
	return (
		<Sheet open={open} onOpenChange={(o) => !o && onClose()}>
			<SheetContent className="w-full space-y-5 overflow-y-auto sm:max-w-md">
				<SheetHeader>
					<SheetTitle>Message</SheetTitle>
					<SheetDescription>{detail ? `${KIND_LABEL[detail.kind] ?? detail.kind} from ${detail.sender_name || detail.sender_id}` : 'Loading'}</SheetDescription>
				</SheetHeader>
				{error ? <LoadError message={error} /> : !detail ? <Skeleton className="h-40 w-full" /> : (
					<dl className="space-y-4">
						<Field label="Text"><p className="whitespace-pre-wrap break-words">{detail.text || <Empty />}</p></Field>
						<Field label="Received"><TimeStamp value={detail.received_at} /></Field>
						<Field label="Update type"><span className="font-mono">{detail.update_kind || '-'}</span></Field>
						<Field label="Chat"><span className="font-mono">{detail.chat_id || '-'}</span></Field>
						<Field label="Status"><Badge variant={tone(detail.status)}>{detail.status || 'Unknown'}</Badge></Field>
						<Field label="Attachments">
							{detail.attachments.length === 0 ? <Empty /> : (
								<ul className="space-y-1">
									{detail.attachments.map((a, i) => (
										<li key={i}>{a.kind}{a.filename ? ` - ${a.filename}` : ''}{a.mime_type ? ` (${a.mime_type})` : ''}</li>
									))}
								</ul>
							)}
						</Field>
						<Field label="Reply">
							{detail.reply.status ? <Badge variant={tone(detail.reply.status)}>{detail.reply.status}</Badge> : <Empty />}
							{detail.reply.parts.length > 0 && <div className="mt-1 text-steel">{detail.reply.parts.length} part(s) sent</div>}
						</Field>
						{(detail.error || detail.reply.error) && (
							<Field label="Error"><span className="break-words text-destructive">{detail.error || detail.reply.error}</span></Field>
						)}
						<Field label="Agent run">{detail.agent_run ? <a className="text-primary underline" href={`/agent-runs/${encodeURIComponent(detail.agent_run)}`}>{detail.agent_run}</a> : <Empty />}</Field>
					</dl>
				)}
			</SheetContent>
		</Sheet>
	);
}
