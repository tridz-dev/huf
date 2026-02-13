/**
 * Full-screen preview page for viewing JSX/artifact content from a message.
 *
 * Route: /huf/view/:messageId
 *
 * Fetches the Agent Message by ID, parses JSX and artifact content,
 * and renders it full-screen with a minimal toolbar.
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
import {
	JSXPreview,
	JSXPreviewContent,
	JSXPreviewExport,
} from '@/components/ui/jsx-preview';
import type { ParsedJSXPreview, ParsedArtifact } from '@/types/artifact.types';

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
	const [jsxPreviews, setJsxPreviews] = useState<ParsedJSXPreview[]>([]);
	const [jsxArtifacts, setJsxArtifacts] = useState<ParsedArtifact[]>([]);
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

				// Parse JSX previews
				const previews: ParsedJSXPreview[] = [];
				const artifacts: ParsedArtifact[] = [];

				if (hasJSXPreviews(decoded)) {
					const parsed = parseJSXPreviews(decoded);
					previews.push(...parsed.previews);
				}

				if (hasArtifacts(decoded)) {
					const parsed = parseArtifacts(decoded);
					const jsxTypes = parsed.artifacts.filter(
						(a) => a.type === 'jsx' || a.type === 'chart'
					);
					artifacts.push(...jsxTypes);
				}

				setJsxPreviews(previews);
				setJsxArtifacts(artifacts);

				if (previews.length === 0 && artifacts.length === 0) {
					setError('No JSX or chart content found in this message');
				}
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

	const allItems = [
		...jsxPreviews.map((p, i) => ({ type: 'preview' as const, data: p, key: `preview-${i}` })),
		...jsxArtifacts.map((a) => ({ type: 'artifact' as const, data: a, key: `artifact-${a.id}` })),
	];

	return (
		<div className="flex h-screen flex-col bg-background">
			{/* Toolbar */}
			<header className="flex items-center justify-between border-b px-4 py-2">
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
						{jsxPreviews.length + jsxArtifacts.length} preview{allItems.length !== 1 ? 's' : ''}
					</span>
				</div>
				<div className="flex items-center gap-2">
					<JSXPreviewExportStandalone containerRef={containerRef} />
				</div>
			</header>

			{/* Content */}
			<main ref={containerRef} className="flex-1 overflow-auto p-6">
				<div className="mx-auto max-w-6xl space-y-6">
					{allItems.map((item) => {
						const jsx =
							item.type === 'preview'
								? (item.data as ParsedJSXPreview).jsx
								: (item.data as ParsedArtifact).content;

						const title =
							item.type === 'preview'
								? (item.data as ParsedJSXPreview).title
								: (item.data as ParsedArtifact).title;

						return (
							<section key={item.key}>
								{title && (
									<h2 className="mb-2 text-sm font-medium text-muted-foreground">
										{title}
									</h2>
								)}
								<JSXPreview jsx={jsx} className="min-h-[300px] w-full">
									<JSXPreviewContent />
								</JSXPreview>
							</section>
						);
					})}
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
