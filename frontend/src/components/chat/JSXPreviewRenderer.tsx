/**
 * Renderer component for standalone JSX preview elements.
 *
 * This component renders JSX preview tags that are NOT inside artifacts.
 * For JSX inside artifacts, see ArtifactRenderer.
 */

import { useCallback } from 'react';
import {
	JSXPreview,
	JSXPreviewContent,
	JSXPreviewExport,
} from '@/components/ui/jsx-preview';
import { Button } from '@/components/ui/button';
import { ExternalLink } from 'lucide-react';
import {
	Tooltip,
	TooltipContent,
	TooltipProvider,
	TooltipTrigger,
} from '@/components/ui/tooltip';
import type { ParsedJSXPreview } from '@/types/artifact.types';

interface JSXPreviewRendererProps {
	preview: ParsedJSXPreview;
	/** Agent Message document name — enables the "Open" button */
	messageId?: string;
}

export function JSXPreviewRenderer({ preview, messageId }: JSXPreviewRendererProps) {
	const handleOpen = useCallback(() => {
		if (!messageId) return;
		window.open(`/huf/view/${messageId}`, '_blank', 'noopener');
	}, [messageId]);

	return (
		<JSXPreview
			jsx={preview.jsx}
			isStreaming={preview.isStreaming}
			className="my-4 min-h-[200px] w-full"
		>
			<div className="absolute top-2 right-2 z-10 flex items-center gap-2">
				<JSXPreviewExport
					filename={preview.title?.replace(/[^a-z0-9]/gi, '_') || 'jsx-preview'}
				/>
				{messageId && !preview.isStreaming && (
					<TooltipProvider>
						<Tooltip>
							<TooltipTrigger asChild>
								<Button
									variant="outline"
									size="sm"
									onClick={handleOpen}
								>
									<ExternalLink size={14} />
								</Button>
							</TooltipTrigger>
							<TooltipContent>
								<p>Open full screen</p>
							</TooltipContent>
						</Tooltip>
					</TooltipProvider>
				)}
			</div>
			<div className="pt-10">
				<JSXPreviewContent />
			</div>
		</JSXPreview>
	);
}

export default JSXPreviewRenderer;
