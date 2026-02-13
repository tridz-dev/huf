/**
 * Full-screen preview page for viewing full message content.
 *
 * Route: /huf/view/:messageId
 *
 * Fetches the Agent Message by ID and renders the full content (text, JSX,
 * web previews, artifacts) in the same structure as chat, full-screen.
 */

import { useEffect, useState, useRef } from 'react';
import { useParams, Link } from 'react-router-dom';
import { ArrowLeft, Loader2, ExternalLink, AlertCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { db } from '@/lib/frappe-sdk';
import { doctype } from '@/data/doctypes';
import { handleFrappeError } from '@/lib/frappe-error';
import { parseJSXPreviews, hasJSXPreviews } from '@/utils/jsxPreviewParser';
import { parseArtifacts, hasArtifacts } from '@/utils/artifactParser';
import { parseWebPreviews, hasWebPreviews } from '@/utils/webPreviewParser';
import { MessageResponse } from '@/components/ai-elements/message';
import { JSXPreviewRenderer } from '@/components/chat/JSXPreviewRenderer';
import { WebPreviewRenderer } from '@/components/chat/WebPreviewRenderer';
import { ArtifactRenderer } from '@/components/chat/ArtifactRenderer';
import type { ParsedJSXPreview, ParsedArtifact, ParsedWebPreview } from '@/types/artifact.types';

interface AgentMessageDoc {
	name: string;
	content: string;
	conversation: string;
	kind?: string;
	role?: string;
	agent?: string;
}

function decodeHtmlEntities(text: string): string {
	if (typeof document === 'undefined') {
		return text
			.replace(/&lt;/g, '<')
			.replace(/&gt;/g, '>')
			.replace(/&quot;/g, '"')
			.replace(/&#39;/g, "'")
			.replace(/&amp;/g, '&');
	}
	const textarea = document.createElement('textarea');
	textarea.innerHTML = text;
	return textarea.value;
}

export function PreviewViewPage() {
	const { messageId } = useParams<{ messageId: string }>();
	const [loading, setLoading] = useState(true);
	const [error, setError] = useState<string | null>(null);
	const [message, setMessage] = useState<AgentMessageDoc | null>(null);
	const [textContent, setTextContent] = useState('');
	const [jsxPreviews, setJsxPreviews] = useState<ParsedJSXPreview[]>([]);
	const [webPreviews, setWebPreviews] = useState<ParsedWebPreview[]>([]);
	const [artifacts, setArtifacts] = useState<ParsedArtifact[]>([]);
	const containerRef = useRef<HTMLDivElement>(null);

	useEffect(() => {
		if (!messageId) {
			setError('No message ID provided');
			setLoading(false);
			return;
		}

		async function fetchMessage() {
			try {
				const doc = await db.getDoc(doctype['Agent Message'], messageId!);
				const agentMessage = doc as unknown as AgentMessageDoc;
				setMessage(agentMessage);

				const decoded = decodeHtmlEntities(agentMessage.content || '');

				// Parse in same order as MessageContentWithArtifacts: JSX → web → artifacts
				let remaining = decoded;
				const previews: ParsedJSXPreview[] = [];
				const web: ParsedWebPreview[] = [];
				const arts: ParsedArtifact[] = [];

				if (hasJSXPreviews(remaining)) {
					const parsed = parseJSXPreviews(remaining);
					remaining = parsed.text;
					previews.push(...parsed.previews);
				}
				if (hasWebPreviews(remaining)) {
					const parsed = parseWebPreviews(remaining);
					remaining = parsed.text;
					web.push(...parsed.previews);
				}
				if (hasArtifacts(remaining)) {
					const parsed = parseArtifacts(remaining);
					remaining = parsed.text;
					arts.push(...parsed.artifacts);
				}

				setTextContent(remaining.replace(/\n{3,}/g, '\n\n').trim());
				setJsxPreviews(previews);
				setWebPreviews(web);
				setArtifacts(arts);
			} catch (err) {
				handleFrappeError(err, 'Error fetching message');
				setError('Failed to load message. It may not exist or you may not have access.');
			} finally {
				setLoading(false);
			}
		}

		fetchMessage();
	}, [messageId]);

	// Loading state
	if (loading) {
		return (
			<div className="flex h-screen items-center justify-center bg-background">
				<div className="flex flex-col items-center gap-3 text-muted-foreground">
					<Loader2 className="size-8 animate-spin" />
					<p className="text-sm">Loading preview...</p>
				</div>
			</div>
		);
	}

	// Error state
	if (error) {
		return (
			<div className="flex h-screen items-center justify-center bg-background">
				<div className="flex max-w-md flex-col items-center gap-4 text-center">
					<AlertCircle className="size-10 text-muted-foreground" />
					<div>
						<p className="font-medium text-foreground">{error}</p>
						<p className="mt-1 text-sm text-muted-foreground">
							Message ID: {messageId}
						</p>
					</div>
					{message?.conversation && (
						<Link to={`/chat/${message.conversation}`}>
							<Button variant="outline" size="sm">
								<ArrowLeft className="mr-2 size-4" />
								Back to chat
							</Button>
						</Link>
					)}
				</div>
			</div>
		);
	}

	const hasContent =
		(textContent && textContent.trim()) ||
		jsxPreviews.length > 0 ||
		webPreviews.length > 0 ||
		artifacts.length > 0;

	return (
		<div className="flex h-screen flex-col bg-background">
			{/* Toolbar */}
			<header className="flex shrink-0 items-center justify-between border-b px-4 py-2">
				<div className="flex items-center gap-3">
					{message?.conversation ? (
						<Link to={`/chat/${message.conversation}`}>
							<Button variant="ghost" size="sm">
								<ArrowLeft className="mr-2 size-4" />
								Back to chat
							</Button>
						</Link>
					) : (
						<Link to="/chat">
							<Button variant="ghost" size="sm">
								<ArrowLeft className="mr-2 size-4" />
								Back
							</Button>
						</Link>
					)}
					<span className="text-sm text-muted-foreground">
						Full message
					</span>
				</div>
				<div className="flex items-center gap-2">
					<JSXPreviewExportStandalone containerRef={containerRef} />
				</div>
			</header>

			{/* Content — same structure as chat: text, JSX, web previews, artifacts */}
			<main ref={containerRef} className="min-h-0 flex-1 overflow-auto p-6">
				<div className="mx-auto max-w-4xl space-y-4">
					{!hasContent ? (
						<p className="text-sm text-muted-foreground">No content in this message.</p>
					) : (
						<>
							{textContent && textContent.trim() && (
								<div className="prose prose-sm dark:prose-invert max-w-none">
									<MessageResponse>{textContent}</MessageResponse>
								</div>
							)}
							{jsxPreviews.map((preview, idx) => (
								<JSXPreviewRenderer
									key={`preview-${idx}`}
									preview={preview}
									/* no messageId: already on view page, hide Open button */
								/>
							))}
							{webPreviews.map((preview, idx) => (
								<WebPreviewRenderer key={`web-${idx}`} preview={preview} />
							))}
							{artifacts.map((artifact) => (
								<ArtifactRenderer
									key={artifact.id}
									artifact={artifact}
									/* no messageId: already on view page */
								/>
							))}
						</>
					)}
				</div>
			</main>
		</div>
	);
}

/**
 * Standalone export buttons for the toolbar.
 * Wraps JSXPreviewExport but takes containerRef as a prop
 * since we're outside the JSXPreview context.
 */
function JSXPreviewExportStandalone({
	containerRef,
}: {
	containerRef: React.RefObject<HTMLDivElement | null>;
}) {
	const [isExporting, setIsExporting] = useState(false);

	const handleExportPng = async () => {
		if (!containerRef.current) return;
		setIsExporting(true);
		try {
			const { toPng } = await import('html-to-image');
			const dataUrl = await toPng(containerRef.current, {
				backgroundColor: '#ffffff',
				pixelRatio: 2,
			});
			const link = document.createElement('a');
			link.download = 'preview.png';
			link.href = dataUrl;
			link.click();
		} catch (err) {
			console.error('Failed to export PNG:', err);
		} finally {
			setIsExporting(false);
		}
	};

	return (
		<Button variant="outline" size="sm" onClick={handleExportPng} disabled={isExporting}>
			<ExternalLink className="mr-2 size-4" />
			{isExporting ? 'Exporting...' : 'Export PNG'}
		</Button>
	);
}

export default PreviewViewPage;
