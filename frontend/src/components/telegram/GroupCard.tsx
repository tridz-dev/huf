import { useState } from 'react';
import { toast } from 'sonner';
import { Loader2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
	AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
	AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { TimeStamp } from '@/components/whatsapp/TimeStamp';
import {
	BOT_RIGHT_LABEL, getGroupSettings, leaveGroup, type GroupSettings, type KnownGroup,
} from '@/services/telegramGroupsApi';

/** One group the bot knows about: live rights and admins on demand, and a confirmed leave. */
export function GroupCard({ gateway, group, onChanged }: { gateway: string; group: KnownGroup; onChanged: () => void }) {
	const [settings, setSettings] = useState<GroupSettings | null>(null);
	const [loading, setLoading] = useState(false);
	const [error, setError] = useState('');
	const [leaving, setLeaving] = useState(false);
	const [busy, setBusy] = useState(false);

	const check = async () => {
		setLoading(true);
		setError('');
		const res = await getGroupSettings(gateway, group.chat_id);
		if (res.ok) setSettings(res.data); else setError(res.error);
		setLoading(false);
	};
	const leave = async () => {
		setBusy(true);
		const res = await leaveGroup(gateway, group.chat_id);
		setBusy(false);
		setLeaving(false);
		if (res.ok) { toast.success('The bot left the group'); onChanged(); } else toast.error(res.error);
	};

	const title = settings?.title || group.title || `Group ${group.chat_id}`;
	const rights = settings?.bot.rights ?? {};
	return (
		<div className="space-y-2 rounded-sm border border-line p-3 text-xs">
			<div className="flex flex-wrap items-center justify-between gap-2">
				<div>
					<div className="font-medium text-ink">{title}</div>
					<div className="font-mono text-steel">{group.chat_id}</div>
				</div>
				<div className="flex items-center gap-2">
					{group.status === 'removed' && <Badge variant="pill-danger">Bot removed</Badge>}
					{settings && <Badge variant={settings.bot.status === 'administrator' ? 'pill-success' : 'pill-warning'}>{settings.bot.status === 'administrator' ? 'Admin' : settings.bot.status || 'Member'}</Badge>}
				</div>
			</div>
			{group.since && <div className="text-steel">Known since <TimeStamp value={group.since} /></div>}
			{error && <p className="text-destructive">{error}</p>}
			{settings && (
				<div className="space-y-1">
					<div className="flex flex-wrap gap-1">
						{Object.keys(BOT_RIGHT_LABEL).map((k) => (
							<Badge key={k} variant={rights[k] ? 'pill-success' : 'pill-neutral'}>{BOT_RIGHT_LABEL[k]}</Badge>
						))}
					</div>
					<div className="text-steel">Admins: {settings.admins.map((a) => a.name || a.user_id).join(', ') || 'none listed'}</div>
				</div>
			)}
			<div className="space-x-2">
				<Button size="sm" variant="outline" disabled={loading} onClick={() => void check()}>
					{loading ? <Loader2 className="h-3 w-3 animate-spin" /> : settings ? 'Refresh' : 'Check rights'}
				</Button>
				{group.status === 'member' && <Button size="sm" variant="outline" onClick={() => setLeaving(true)}>Leave group</Button>}
			</div>
			<AlertDialog open={leaving} onOpenChange={(o) => !o && !busy && setLeaving(false)}>
				<AlertDialogContent>
					<AlertDialogHeader>
						<AlertDialogTitle>Leave {title}?</AlertDialogTitle>
						<AlertDialogDescription>The bot will stop answering in this group. An admin has to add it back to return.</AlertDialogDescription>
					</AlertDialogHeader>
					<AlertDialogFooter>
						<AlertDialogCancel disabled={busy}>Cancel</AlertDialogCancel>
						<AlertDialogAction disabled={busy} onClick={(e) => { e.preventDefault(); void leave(); }}>Leave group</AlertDialogAction>
					</AlertDialogFooter>
				</AlertDialogContent>
			</AlertDialog>
		</div>
	);
}
