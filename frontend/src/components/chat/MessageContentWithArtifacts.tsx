/**
 * Helper component that parses and renders message content with artifacts, web previews, and JSX previews.
 * Extracts <artifact>, <web-preview>, and <jsx-preview> tags from content and renders them as components.
 */

import { MessageResponse } from '@/components/ai-elements/message';
import { ArtifactRenderer } from './ArtifactRenderer';
import { WebPreviewRenderer } from './WebPreviewRenderer';
import { JSXPreviewRenderer } from './JSXPreviewRenderer';
import { hasArtifacts } from '@/utils/artifactParser';
import { hasWebPreviews } from '@/utils/webPreviewParser';
import { hasJSXPreviews } from '@/utils/jsxPreviewParser';
import { parseMessagePreviewContent } from '@/utils/messageContentParser';
import { decodeHtmlEntities } from '@/utils/decodeHtmlEntities';

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

	if (!contentHasArtifacts && !contentHasWebPreviews && !contentHasJSXPreviews) {
		return <MessageResponse>{content}</MessageResponse>;
	}

	const parsed = parseMessagePreviewContent(content);
	const { textContent, jsxPreviews, webPreviews, artifacts } = parsed;

	return (
		<>
			{textContent && textContent.trim() && (
				<MessageResponse>{textContent}</MessageResponse>
			)}

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
