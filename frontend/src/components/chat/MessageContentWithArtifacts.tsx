/**
 * Helper component that parses and renders message content with artifacts, web previews, and JSX previews.
 * Extracts <artifact>, <web-preview>, and <jsx-preview> tags from content and renders them as components.
 */

import { MessageResponse } from '@/components/ai-elements/message';
import { ArtifactRenderer } from './ArtifactRenderer';
import { WebPreviewRenderer } from './WebPreviewRenderer';
import { JSXPreviewRenderer } from './JSXPreviewRenderer';
import { parseArtifacts, hasArtifacts } from '@/utils/artifactParser';
import { parseWebPreviews, hasWebPreviews } from '@/utils/webPreviewParser';
import { parseJSXPreviews, hasJSXPreviews } from '@/utils/jsxPreviewParser';
import type { ParsedArtifact, ParsedWebPreview, ParsedJSXPreview } from '@/types/artifact.types';

/**
 * Decode HTML entities in content to handle escaped tags like &lt;web-preview&gt;.
 * Uses pure string replacement instead of the DOM parser to avoid mutation-XSS.
 */
function decodeHtmlEntities(text: string): string {
	// Decode &amp; last to avoid double-decoding inputs like &amp;lt;.
	return text
		.replace(/&lt;/g, '<')
		.replace(/&gt;/g, '>')
		.replace(/&quot;/g, '"')
		.replace(/&#39;/g, "'")
		.replace(/&amp;/g, '&');
}

interface MessageContentWithArtifactsProps {
	content: string;
	messageKey: string;
}

export function MessageContentWithArtifacts({ content, messageKey }: MessageContentWithArtifactsProps) {
	// Decode HTML entities first (handles &lt;web-preview&gt; → <web-preview>)
	const decodedContent = decodeHtmlEntities(content);

	// Check if content has artifacts, web previews, or JSX previews
	const contentHasArtifacts = hasArtifacts(decodedContent);
	const contentHasWebPreviews = hasWebPreviews(decodedContent);
	const contentHasJSXPreviews = hasJSXPreviews(decodedContent);

	// If no special content, render as plain markdown
	if (!contentHasArtifacts && !contentHasWebPreviews && !contentHasJSXPreviews) {
		return <MessageResponse>{content}</MessageResponse>;
	}

	// Parse in order: JSX previews → web previews → artifacts
	// This prevents nested tags from being captured incorrectly
	let textContent = decodedContent;
	let artifacts: ParsedArtifact[] = [];
	let webPreviews: ParsedWebPreview[] = [];
	let jsxPreviews: ParsedJSXPreview[] = [];

	if (contentHasJSXPreviews) {
		const parsed = parseJSXPreviews(textContent);
		textContent = parsed.text;
		jsxPreviews = parsed.previews;
	}

	if (contentHasWebPreviews) {
		const parsed = parseWebPreviews(textContent);
		textContent = parsed.text;
		webPreviews = parsed.previews;
	}

	if (contentHasArtifacts) {
		const parsed = parseArtifacts(textContent);
		textContent = parsed.text;
		artifacts = parsed.artifacts;
	}

	return (
		<>
			{/* Render text content if any remains */}
			{textContent && textContent.trim() && (
				<MessageResponse>{textContent}</MessageResponse>
			)}

		{/* Render JSX previews */}
		{jsxPreviews.map((preview, idx) => (
			<JSXPreviewRenderer key={`${messageKey}-jsx-${idx}`} preview={preview} messageId={messageKey} />
		))}

		{/* Render web previews */}
		{webPreviews.map((preview, idx) => (
			<WebPreviewRenderer key={`${messageKey}-preview-${idx}`} preview={preview} />
		))}

		{/* Render artifacts */}
		{artifacts.map((artifact) => (
			<ArtifactRenderer key={`${messageKey}-${artifact.id}`} artifact={artifact} messageId={messageKey} />
		))}
		</>
	);
}
