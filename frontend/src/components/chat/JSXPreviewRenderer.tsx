/**
 * Renderer component for standalone JSX preview elements.
 *
 * This component renders JSX preview tags that are NOT inside artifacts.
 * For JSX inside artifacts, see ArtifactRenderer.
 */

import {
	JSXPreview,
	JSXPreviewContent,
	JSXPreviewExport,
} from '@/components/ui/jsx-preview';
import type { ParsedJSXPreview } from '@/types/artifact.types';

interface JSXPreviewRendererProps {
	preview: ParsedJSXPreview;
}

export function JSXPreviewRenderer({ preview }: JSXPreviewRendererProps) {
	return (
		<JSXPreview
			jsx={preview.jsx}
			isStreaming={preview.isStreaming}
			className="my-4 min-h-[200px]"
		>
			<JSXPreviewContent />
			{preview.title && (
				<div className="absolute top-2 right-2">
					<JSXPreviewExport
						filename={preview.title.replace(/[^a-z0-9]/gi, '_') || 'jsx-preview'}
					/>
				</div>
			)}
		</JSXPreview>
	);
}

export default JSXPreviewRenderer;
