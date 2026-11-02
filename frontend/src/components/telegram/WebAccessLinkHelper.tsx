import { useState } from 'react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { getWebAccessUrl } from '@/services/telegramWebAccessApi';
import { webAccessFallbackUrl } from './settingsModel';

/** Builds and copies the Mini App link for one page. */
export function WebAccessLinkHelper({ gateway }: { gateway: string }) {
	const [to, setTo] = useState('');
	const [link, setLink] = useState('');
	const [busy, setBusy] = useState(false);

	const onCopy = async () => {
		setBusy(true);
		const res = await getWebAccessUrl(gateway, to.trim());
		setBusy(false);
		const url = res.ok && res.data.url ? res.data.url : webAccessFallbackUrl(window.location.origin, gateway, to.trim());
		setLink(url);
		try {
			await navigator.clipboard.writeText(url);
			toast.success('Link copied.');
		} catch {
			toast.error('Could not copy. Select the link below instead.');
		}
	};

	return (
		<div className="space-y-2 rounded-md border border-line p-3">
			<Label htmlFor="tg-web-link-page" className="text-sm text-ink">Copy link</Label>
			<div className="flex flex-col gap-2 sm:flex-row">
				<Input
					id="tg-web-link-page"
					value={to}
					placeholder="/app/query-report/Sales Register"
					onChange={(e) => setTo(e.target.value)}
				/>
				<Button type="button" variant="outline" disabled={busy} onClick={onCopy}>Copy link</Button>
			</div>
			{link && <Input readOnly aria-label="Mini App link" value={link} onFocus={(e) => e.currentTarget.select()} />}
			<p className="text-xs text-steel">
				Paste it as the menu button address under Commands, or let the agent send it as a web app button.
			</p>
		</div>
	);
}
