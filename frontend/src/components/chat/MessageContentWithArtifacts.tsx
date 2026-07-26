/**
 * Helper component that parses and renders message content with artifacts, web previews,
 * JSX previews, and structured UI components.
 * Extracts <ui-component>, <artifact>, <web-preview>, and <jsx-preview> tags from content
 * and renders them as components.
 * Parse order: UI components → JSX previews → web previews → artifacts.
 */

import { MessageResponse } from '@/components/ai-elements/message';
import { ArtifactRenderer } from './ArtifactRenderer';
import { WebPreviewRenderer } from './WebPreviewRenderer';
import { JSXPreviewRenderer } from './JSXPreviewRenderer';
import { UIComponentRenderer } from './ui-components/UIComponentRenderer';
import { hasArtifacts } from '@/utils/artifactParser';
import { hasWebPreviews } from '@/utils/webPreviewParser';
import { hasJSXPreviews } from '@/utils/jsxPreviewParser';
import { parseMessagePreviewContent } from '@/utils/messageContentParser';
import { decodeHtmlEntities } from '@/utils/decodeHtmlEntities';
import { parseUIComponents, hasUIComponents } from './ui-components/uiComponentParser';
import type { ParsedUIComponent } from '@/types/artifact.types';

interface MessageContentWithArtifactsProps {
	content: string;
	/** Agent Message document name for preview links */
	messageId: string;
}

export function MessageContentWithArtifacts({ content, messageId }: MessageContentWithArtifactsProps) {
	const decodedContent = decodeHtmlEntities(content);

	const contentHasArtifacts = hasArtifacts(decodedContent);
	const contentHasWebPreviews = hasWebPreviews(decodedContent);
	const contentHasJSXPreviews = hasJSXPreviews(decodedContent);
	const contentHasUIComponents = hasUIComponents(decodedContent);

	if (!contentHasArtifacts && !contentHasWebPreviews && !contentHasJSXPreviews && !contentHasUIComponents) {
		return (
			<div className="min-w-0 max-w-full overflow-x-auto">
				<MessageResponse>{content}</MessageResponse>
			</div>
		);
	}

	// Extract UI components first so the shared preview pipeline never sees
	// <ui-component> tags (parse order: UI → JSX → web-preview → artifact).
	let uiComponents: ParsedUIComponent[] = [];
	let remainingContent = content;
	if (contentHasUIComponents) {
		const parsedUI = parseUIComponents(decodedContent);
		uiComponents = parsedUI.components;
		remainingContent = parsedUI.text;
	}

	const parsed = parseMessagePreviewContent(remainingContent);
	const { textContent, jsxPreviews, webPreviews, artifacts } = parsed;

	return (
		<>
			{textContent && textContent.trim() && (
				<div className="min-w-0 max-w-full overflow-x-auto">
					<MessageResponse>{textContent}</MessageResponse>
				</div>
			)}

			{uiComponents.map((comp, idx) => (
				<UIComponentRenderer key={`${messageId}-ui-${idx}`} component={comp} />
			))}

			{jsxPreviews.map((preview, idx) => (
				<JSXPreviewRenderer
					key={`${messageId}-jsx-${idx}`}
					preview={preview}
					messageId={messageId}
					previewContent={parsed}
				/>
			))}

			{webPreviews.map((preview, idx) => (
				<WebPreviewRenderer key={`${messageId}-preview-${idx}`} preview={preview} />
			))}

			{artifacts.map((artifact) => (
				<ArtifactRenderer
					key={`${messageId}-${artifact.id}`}
					artifact={artifact}
					messageId={messageId}
					previewContent={parsed}
				/>
			))}
		</>
	);
}
