import { useCallback, useEffect, useRef, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { LoadError } from '@/components/whatsapp/BridgeUnavailable';
import { TimeStamp } from '@/components/whatsapp/TimeStamp';
import {
	getMessage, KIND_LABEL, listMessages, MESSAGE_KINDS, MESSAGE_STATUSES, statusTone,
	type MessageFilters, type MessageKind, type TelegramMessage, type TelegramMessageDetail,
} from '@/services/telegramMessagesApi';
import { MessageDetailSheet } from './MessageDetailSheet';

const ALL = '__all__';
const tone = (s: string) => (statusTone(s) === 'good' ? 'pill-success' : statusTone(s) === 'bad' ? 'pill-danger' : 'pill-warning');

/** Inbound Telegram messages for one gateway, newest first, with filters and a detail drawer. */
export function MessagesTab({ gateway }: { gateway: string }) {
	const [filters, setFilters] = useState<MessageFilters>({});
	const [query, setQuery] = useState('');
	const [items, setItems] = useState<TelegramMessage[]>([]);
	const [cursor, setCursor] = useState<string | null>(null);
	const [loading, setLoading] = useState(true);
	const [error, setError] = useState('');
	const [openName, setOpenName] = useState<string | null>(null);
	const [detail, setDetail] = useState<TelegramMessageDetail | null>(null);
	const [detailError, setDetailError] = useState('');
	const token = useRef(0);

	const load = useCallback(async (more: boolean, from: string | null) => {
		const id = ++token.current;
		setLoading(true);
		setError('');
		const res = await listMessages(gateway, filters, more ? from : null);
		if (id !== token.current) return;
		if (res.ok) {
			setItems((prev) => (more ? [...prev, ...res.data.items] : res.data.items));
			setCursor(res.data.has_more ? res.data.next_cursor : null);
		} else {
			if (!more) setItems([]);
			setError(res.error);
		}
		setLoading(false);
	}, [gateway, filters]);
	useEffect(() => { void load(false, null); }, [load]);
	useEffect(() => {
		const t = setTimeout(() => setFilters((f) => (f.q === (query || undefined) ? f : { ...f, q: query || undefined })), 300);
		return () => clearTimeout(t);
	}, [query]);

	const open = async (name: string) => {
		setOpenName(name);
		setDetail(null);
		setDetailError('');
		const res = await getMessage(gateway, name);
		if (res.ok) setDetail(res.data.message);
		else setDetailError(res.error);
	};

	return (
		<div className="space-y-3">
			<div className="flex flex-wrap items-center gap-2">
				<Select value={filters.status ?? ALL} onValueChange={(v) => setFilters((f) => ({ ...f, status: v === ALL ? undefined : v }))}>
					<SelectTrigger className="w-40" aria-label="Status"><SelectValue placeholder="Status" /></SelectTrigger>
					<SelectContent>
						<SelectItem value={ALL}>Any status</SelectItem>
						{MESSAGE_STATUSES.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
					</SelectContent>
				</Select>
				<Select value={filters.kind || ALL} onValueChange={(v) => setFilters((f) => ({ ...f, kind: v === ALL ? '' : (v as MessageKind) }))}>
					<SelectTrigger className="w-44" aria-label="Kind"><SelectValue placeholder="Kind" /></SelectTrigger>
					<SelectContent>
						<SelectItem value={ALL}>Any kind</SelectItem>
						{MESSAGE_KINDS.map((k) => <SelectItem key={k} value={k}>{KIND_LABEL[k]}</SelectItem>)}
					</SelectContent>
				</Select>
				<Input className="w-56" placeholder="Search text or sender" aria-label="Search" value={query} onChange={(e) => setQuery(e.target.value)} />
			</div>
			{error && <LoadError message={error} onRetry={() => void load(false, null)} />}
			{!error && !loading && items.length === 0 ? (
				<p className="rounded-sm border border-line p-6 text-center text-xs text-steel">No messages match.</p>
			) : items.length > 0 ? (
				<div className="rounded-sm border border-line">
					<Table>
						<TableHeader>
							<TableRow>
								<TableHead>From</TableHead><TableHead>Kind</TableHead><TableHead>Message</TableHead><TableHead>Status</TableHead><TableHead>Received</TableHead>
							</TableRow>
						</TableHeader>
						<TableBody>
							{items.map((m) => (
								<TableRow key={m.name} className="cursor-pointer" onClick={() => void open(m.name)}>
									<TableCell className="text-xs">
										<div className="text-ink">{m.sender_name || m.sender_id}</div>
										{m.sender_name && <div className="font-mono text-steel">{m.sender_id}</div>}
									</TableCell>
									<TableCell className="text-xs">{KIND_LABEL[m.kind] ?? m.kind}</TableCell>
									<TableCell className="max-w-xs truncate text-xs">{m.text || '-'}</TableCell>
									<TableCell>
										<Badge variant={tone(m.status)}>{m.status || 'Unknown'}</Badge>
										{m.reply_status && <div className="mt-0.5 text-[11px] text-steel">Reply: {m.reply_status}</div>}
									</TableCell>
									<TableCell className="whitespace-nowrap text-xs text-steel"><TimeStamp value={m.received_at} /></TableCell>
								</TableRow>
							))}
						</TableBody>
					</Table>
				</div>
			) : null}
			{loading && <div className="flex items-center gap-2 text-xs text-steel"><Loader2 className="h-4 w-4 animate-spin" /> Loading...</div>}
			{cursor && !loading && <Button variant="outline" size="sm" onClick={() => void load(true, cursor)}>Load more</Button>}
			<MessageDetailSheet open={!!openName} detail={detail} error={detailError} onClose={() => setOpenName(null)} />
		</div>
	);
}
