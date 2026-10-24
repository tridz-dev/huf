import { useMemo, useState, type ReactNode } from 'react';
import { Copy, ExternalLink, FileText, Image as ImageIcon, Link2, Mic, Music, Play, Search, Smile } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { TemplateDraft } from '@/services/telegramTemplatesApi';
import { buildBubble, type ButtonKind, type FormatNode } from './previewModel';

const BUTTON_ICON: Partial<Record<ButtonKind, typeof Copy>> = {
	url: ExternalLink, web_app: ExternalLink, login_url: ExternalLink, copy_text: Copy, switch_inline: Search,
};
const MEDIA_ICON: Record<string, typeof FileText> = {
	photo: ImageIcon, video: Play, animation: Play, document: FileText, audio: Music, voice: Mic, sticker: Smile,
};

function Spoiler({ children }: { children: ReactNode }) {
	const [open, setOpen] = useState(false);
	return (
		<span
			role="button"
			tabIndex={0}
			aria-label={open ? undefined : 'Hidden text, press to reveal'}
			onClick={() => setOpen(true)}
			onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && setOpen(true)}
			className={cn('rounded-sm px-0.5', open ? 'bg-line/40' : 'cursor-pointer bg-steel text-transparent select-none')}
		>
			{children}
		</span>
	);
}

function renderNodes(nodes: FormatNode[]): ReactNode {
	return nodes.map((n, i) => {
		switch (n.kind) {
			case 'text': return <span key={i}>{n.value}</span>;
			case 'code': return <code key={i} className="rounded bg-line/40 px-1 font-mono text-[0.9em]">{n.value}</code>;
			case 'pre': return <pre key={i} className="my-1 overflow-x-auto rounded bg-line/40 p-2 font-mono text-xs">{n.value}</pre>;
			case 'bold': return <strong key={i}>{renderNodes(n.children)}</strong>;
			case 'italic': return <em key={i}>{renderNodes(n.children)}</em>;
			case 'underline': return <u key={i}>{renderNodes(n.children)}</u>;
			case 'strike': return <s key={i}>{renderNodes(n.children)}</s>;
			case 'spoiler': return <Spoiler key={i}>{renderNodes(n.children)}</Spoiler>;
			case 'quote': return <blockquote key={i} className="my-1 border-l-2 border-signal pl-2">{renderNodes(n.children)}</blockquote>;
			case 'link': return <span key={i} className="text-signal-ink underline">{renderNodes(n.children)}</span>;
		}
	});
}

const WALLPAPER = { backgroundImage: 'radial-gradient(var(--line) 1px, transparent 1px)', backgroundSize: '14px 14px' } as const;

export interface TemplatePreviewProps {
	draft: TemplateDraft;
	/** Values typed into the "try it" fields; falls back to defaults then examples. */
	values?: Record<string, string>;
	className?: string;
}

/** A message bubble the way it will look in Telegram: media header, formatted text, inline buttons. */
export function TemplatePreview({ draft, values, className }: TemplatePreviewProps) {
	const bubble = useMemo(() => buildBubble(draft, values), [draft, values]);
	const empty = !bubble.media && !draft.body.trim() && bubble.rows.length === 0;
	const MediaIcon = bubble.media ? (MEDIA_ICON[bubble.media.type] ?? FileText) : null;
	const showImage = bubble.media?.type === 'photo' && /^(https?:\/\/|\/)/.test(bubble.media.url);
	return (
		<div className={cn('rounded-md border border-line bg-paper-deep p-4', className)} style={WALLPAPER} aria-label="Message preview">
			{empty ? (
				<p className="py-6 text-center text-xs text-steel">Your message preview appears here as you type.</p>
			) : (
				<div className="max-w-[320px]">
					<div className="overflow-hidden rounded-lg rounded-tl-none border border-line bg-panel shadow-sm">
						{bubble.media && MediaIcon && (
							showImage ? (
								<img src={bubble.media.url} alt="" className="max-h-48 w-full object-cover" data-testid="preview-media" />
							) : (
								<div className="flex h-28 flex-col items-center justify-center gap-1 bg-line/30 text-steel" data-testid="preview-media">
									<MediaIcon className="h-8 w-8" aria-hidden />
									<span className="max-w-full truncate px-3 text-xs">{bubble.media.url.split('/').pop() || bubble.media.type}</span>
								</div>
							)
						)}
						{(draft.body.trim() || !bubble.media) && (
							<div className="px-3 py-2">
								<div className="whitespace-pre-wrap break-words text-sm text-ink" data-testid="preview-body">{renderNodes(bubble.nodes)}</div>
								<p className="text-right text-[11px] text-steel">12:00</p>
							</div>
						)}
					</div>
					{bubble.rows.length > 0 && (
						<div className="mt-1 space-y-1" data-testid="preview-buttons">
							{bubble.rows.map((row, ri) => (
								<div key={ri} className="flex gap-1">
									{row.map((b, bi) => {
										const Icon = BUTTON_ICON[b.kind] ?? Link2;
										return (
											<div key={bi} className="flex min-w-0 flex-1 items-center justify-center gap-1 rounded-lg bg-panel/90 px-2 py-1.5 text-sm font-medium text-signal-ink shadow-sm" data-testid="preview-button">
												{b.kind !== 'callback' && <Icon className="h-3 w-3 shrink-0" aria-hidden />}
												<span className="truncate">{b.text || 'Button'}</span>
											</div>
										);
									})}
								</div>
							))}
						</div>
					)}
				</div>
			)}
			{bubble.missing.length > 0 && (
				<p className="mt-2 text-xs text-steel">No sample for: {bubble.missing.map((m) => `{{${m}}}`).join(', ')}</p>
			)}
			{bubble.overLimit && <p className="mt-2 text-xs text-danger">The text is longer than Telegram allows.</p>}
		</div>
	);
}
