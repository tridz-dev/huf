/**
 * Helper component that parses and renders message content with structured blocks.
 *
 * Extracts <artifact>, <web-preview>, <jsx-preview>, and <ui-component> tags
 * from content and renders them using the appropriate component.
 */

import { MessageResponse } from '@/components/ai-elements/message';
import { ArtifactRenderer } from './ArtifactRenderer';
import { WebPreviewRenderer } from './WebPreviewRenderer';
import { JSXPreviewRenderer } from './JSXPreviewRenderer';
import { UIComponentRenderer } from './ui-components/UIComponentRenderer';
import { parseArtifacts, hasArtifacts } from '@/utils/artifactParser';
import { parseWebPreviews, hasWebPreviews } from '@/utils/webPreviewParser';
import { parseJSXPreviews, hasJSXPreviews } from '@/utils/jsxPreviewParser';
import { parseUIComponents, hasUIComponents } from '@/utils/uiComponentParser';
import type { ParsedArtifact, ParsedWebPreview, ParsedJSXPreview, ParsedUIComponent } from '@/types/artifact.types';

/**
 * Decode HTML entities in content to handle escaped tags like &lt;web-preview&gt;
 * This handles cases where the backend sends HTML-escaped content.
 */
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

interface MessageContentWithArtifactsProps {
	content: string;
	messageKey: string;
}

export function MessageContentWithArtifacts({ content, messageKey }: MessageContentWithArtifactsProps) {
	const decodedContent = decodeHtmlEntities(content);

	const contentHasArtifacts = hasArtifacts(decodedContent);
	const contentHasWebPreviews = hasWebPreviews(decodedContent);
	const contentHasJSXPreviews = hasJSXPreviews(decodedContent);
	const contentHasUIComponents = hasUIComponents(decodedContent);

	if (!contentHasArtifacts && !contentHasWebPreviews && !contentHasJSXPreviews && !contentHasUIComponents) {
		return <MessageResponse>{content}</MessageResponse>;
	}

	// Parse in order: UI components → JSX previews → web previews → artifacts
	let textContent = decodedContent;
	let uiComponents: ParsedUIComponent[] = [];
	let artifacts: ParsedArtifact[] = [];
	let webPreviews: ParsedWebPreview[] = [];
	let jsxPreviews: ParsedJSXPreview[] = [];

	if (contentHasUIComponents) {
		const parsed = parseUIComponents(textContent);
		textContent = parsed.text;
		uiComponents = parsed.components;
	}

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
			{textContent && textContent.trim() && (
				<MessageResponse>{textContent}</MessageResponse>
			)}

		{uiComponents.map((comp, idx) => (
			<UIComponentRenderer key={`${messageKey}-ui-${idx}`} component={comp} />
		))}

		{jsxPreviews.map((preview, idx) => (
			<JSXPreviewRenderer key={`${messageKey}-jsx-${idx}`} preview={preview} messageId={messageKey} />
		))}

		{webPreviews.map((preview, idx) => (
			<WebPreviewRenderer key={`${messageKey}-preview-${idx}`} preview={preview} />
		))}

		{artifacts.map((artifact) => (
			<ArtifactRenderer key={`${messageKey}-${artifact.id}`} artifact={artifact} messageId={messageKey} />
		))}
		</>
	);
}
