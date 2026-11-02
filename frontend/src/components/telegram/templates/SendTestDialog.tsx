import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { sendTestTemplate, type TemplateDraft } from '@/services/telegramTemplatesApi';
import { TemplatePreview } from './TemplatePreview';

export interface SendTestDialogProps {
	/** The saved template to send; null closes the dialog. */
	template: TemplateDraft | null;
	gateway: string;
	onClose: () => void;
}

export function SendTestDialog({ template, gateway, onClose }: SendTestDialogProps) {
	const [chatId, setChatId] = useState('');
	const [values, setValues] = useState<Record<string, string>>({});
	const [confirmed, setConfirmed] = useState(false);
	const [busy, setBusy] = useState(false);
	const [error, setError] = useState('');
	useEffect(() => {
		if (template) { setChatId(''); setValues({}); setConfirmed(false); setError(''); }
	}, [template]);

	const chatOk = /^-?\d{1,20}$/.test(chatId.trim());
	const send = async () => {
		if (!template?.name) return;
		setBusy(true);
		setError('');
		const res = await sendTestTemplate({ gateway, chatId, name: template.name, variables: values });
		setBusy(false);
		if (res.ok) {
			toast.success('Test message sent');
			onClose();
		} else setError(res.error);
	};

	return (
		<Dialog open={!!template} onOpenChange={(o) => !o && onClose()}>
			<DialogContent className="max-h-[85vh] max-w-3xl overflow-y-auto">
				<DialogHeader>
					<DialogTitle>Send a test message</DialogTitle>
					<DialogDescription>
						Test messages go only to a chat you paired yourself, or one whose access notes say "telegram-test".
					</DialogDescription>
				</DialogHeader>
				{template && (
					<div className="grid gap-5 md:grid-cols-[1fr_300px]">
						<div className="space-y-3">
							<div className="space-y-1">
								<Label htmlFor="tg-test-chat">Telegram chat id</Label>
								<Input id="tg-test-chat" inputMode="numeric" className="font-mono" placeholder="123456789" value={chatId} onChange={(e) => setChatId(e.target.value)} />
								{chatId && !chatOk && <p role="alert" className="text-xs text-danger">Enter the numeric chat id (not a username).</p>}
							</div>
							{template.variables.map((v) => (
								<div key={v.variable} className="space-y-1">
									<Label htmlFor={`tg-test-${v.variable}`} className="font-mono">{`{{${v.variable}}}`}</Label>
									<Input id={`tg-test-${v.variable}`} placeholder={v.default_value || v.example} value={values[v.variable] ?? ''} onChange={(e) => setValues({ ...values, [v.variable]: e.target.value })} />
								</div>
							))}
							<label className="flex items-start gap-2 text-sm">
								<Checkbox checked={confirmed} onCheckedChange={(c) => setConfirmed(c === true)} aria-label="Confirm sending" />
								<span>Send this message to Telegram chat {chatId.trim() || '…'} now.</span>
							</label>
							{error && <p role="alert" className="text-sm text-danger">{error}</p>}
						</div>
						<TemplatePreview draft={template} values={values} />
					</div>
				)}
				<DialogFooter>
					<Button variant="outline" onClick={onClose}>Cancel</Button>
					<Button onClick={send} disabled={busy || !chatOk || !confirmed}>
						{busy && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}Send test
					</Button>
				</DialogFooter>
			</DialogContent>
		</Dialog>
	);
}
