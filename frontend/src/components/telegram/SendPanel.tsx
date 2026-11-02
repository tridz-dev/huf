import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { LoadError } from '@/components/whatsapp/BridgeUnavailable';
import {
	listSendTargets, sendTelegramMessage, uploadPrivateFile, validateSend,
	type SendKind, type SendTarget,
} from '@/services/telegramMessagesApi';

const KINDS: { value: SendKind; label: string; accept?: string }[] = [
	{ value: 'text', label: 'Text' },
	{ value: 'photo', label: 'Photo', accept: 'image/jpeg,image/png,image/webp' },
	{ value: 'document', label: 'Document' },
	{ value: 'voice', label: 'Voice note', accept: 'audio/ogg,audio/mpeg,audio/mp4,audio/x-m4a' },
];

/** Send a message as the bot. Only approved people and your own bound chat can be chosen. */
export function SendPanel({ gateway }: { gateway: string }) {
	const [targets, setTargets] = useState<SendTarget[]>([]);
	const [loadError, setLoadError] = useState('');
	const [chat, setChat] = useState('');
	const [kind, setKind] = useState<SendKind>('text');
	const [text, setText] = useState('');
	const [attached, setAttached] = useState<File | null>(null);
	const [busy, setBusy] = useState(false);
	const [error, setError] = useState('');

	useEffect(() => {
		let live = true;
		void listSendTargets(gateway).then((res) => {
			if (!live) return;
			if (res.ok) { setTargets(res.data.items); setChat((c) => c || res.data.items[0]?.chat_id || ''); }
			else setLoadError(res.error);
		});
		return () => { live = false; };
	}, [gateway]);

	const submit = async () => {
		const problem = validateSend(kind, text, attached);
		if (problem) { setError(problem); return; }
		setError('');
		setBusy(true);
		let fileUrl: string | undefined;
		if (kind !== 'text' && attached) {
			const up = await uploadPrivateFile(attached);
			if (!up.ok) { setError(up.error); setBusy(false); return; }
			fileUrl = up.data.fileUrl;
		}
		const res = await sendTelegramMessage(gateway, chat, text, kind, fileUrl);
		setBusy(false);
		if (res.ok) { toast.success('Sent'); setText(''); setAttached(null); }
		else setError(res.error);
	};

	if (loadError) return <LoadError message={loadError} />;
	return (
		<div className="max-w-xl space-y-4">
			{targets.length === 0 ? (
				<p className="rounded-sm border border-line p-6 text-xs text-steel">
					Nobody to send to yet. Approve a person on the Access tab, or bind your own Telegram chat on the Bindings tab.
				</p>
			) : (
				<>
					<div className="space-y-1.5">
						<Label>To</Label>
						<Select value={chat} onValueChange={setChat}>
							<SelectTrigger aria-label="To"><SelectValue placeholder="Choose a chat" /></SelectTrigger>
							<SelectContent>
								{targets.map((t) => <SelectItem key={t.chat_id} value={t.chat_id}>{t.label} ({t.chat_id})</SelectItem>)}
							</SelectContent>
						</Select>
					</div>
					<div className="space-y-1.5">
						<Label>Type</Label>
						<Select value={kind} onValueChange={(v) => { setKind(v as SendKind); setAttached(null); setError(''); }}>
							<SelectTrigger aria-label="Type"><SelectValue /></SelectTrigger>
							<SelectContent>{KINDS.map((k) => <SelectItem key={k.value} value={k.value}>{k.label}</SelectItem>)}</SelectContent>
						</Select>
					</div>
					{kind !== 'text' && (
						<div className="space-y-1.5">
							<Label htmlFor="tg-send-file">File</Label>
							<Input id="tg-send-file" type="file" accept={KINDS.find((k) => k.value === kind)?.accept} onChange={(e) => setAttached(e.target.files?.[0] ?? null)} />
						</div>
					)}
					<div className="space-y-1.5">
						<Label htmlFor="tg-send-text">{kind === 'text' ? 'Message' : 'Caption (optional)'}</Label>
						<Textarea id="tg-send-text" rows={4} value={text} onChange={(e) => setText(e.target.value)} />
					</div>
					{error && <p role="alert" className="text-xs text-destructive">{error}</p>}
					<Button disabled={busy || !chat} onClick={() => void submit()}>
						{busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}Send
					</Button>
				</>
			)}
		</div>
	);
}
