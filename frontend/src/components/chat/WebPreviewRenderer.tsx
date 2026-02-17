/**
 * Renderer component for AI-generated web previews.
 *
 * This component takes a parsed web preview URL and renders it in an iframe
 * with navigation controls.
 */

import { useCallback, useState } from 'react';
import {
	WebPreview,
	WebPreviewNavigation,
	WebPreviewNavigationButton,
	WebPreviewUrl,
	WebPreviewBody,
} from '@/components/ai-elements/web-preview';
import {
	ArrowLeftIcon,
	ArrowRightIcon,
	RefreshCwIcon,
	ExternalLinkIcon,
	XIcon,
	GlobeIcon,
} from 'lucide-react';
import type { ParsedWebPreview } from '@/types/artifact.types';
import { isValidPreviewUrl } from '@/utils/webPreviewParser';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';

interface WebPreviewRendererProps {
	preview: ParsedWebPreview;
	onClose?: () => void;
	className?: string;
}

export function WebPreviewRenderer({
	preview,
	onClose,
	className,
}: WebPreviewRendererProps) {
	const [key, setKey] = useState(0);
	const [isLoading, setIsLoading] = useState(true);
	const [hasError, setHasError] = useState(false);

	const handleRefresh = useCallback(() => {
		setKey((prev) => prev + 1);
		setIsLoading(true);
		setHasError(false);
	}, []);

	const handleOpenInNewTab = useCallback(() => {
		window.open(preview.url, '_blank', 'noopener,noreferrer');
	}, [preview.url]);

	const handleIframeLoad = useCallback(() => {
		setIsLoading(false);
	}, []);

	const handleIframeError = useCallback(() => {
		setIsLoading(false);
		setHasError(true);
	}, []);

	// Validate URL before rendering
	if (!isValidPreviewUrl(preview.url)) {
		return (
			<div className={cn('my-4 p-4 border rounded-lg bg-destructive/10', className)}>
				<p className="text-sm text-destructive">
					Invalid URL: {preview.url}
				</p>
			</div>
		);
	}

	return (
		<WebPreview
			defaultUrl={preview.url}
			className={cn('my-4 h-96', className)}
		>
			<WebPreviewNavigation>
				<WebPreviewNavigationButton tooltip="Back" disabled>
					<ArrowLeftIcon size={16} />
				</WebPreviewNavigationButton>
				<WebPreviewNavigationButton tooltip="Forward" disabled>
					<ArrowRightIcon size={16} />
				</WebPreviewNavigationButton>
				<WebPreviewNavigationButton tooltip="Refresh" onClick={handleRefresh}>
					<RefreshCwIcon size={16} className={isLoading ? 'animate-spin' : ''} />
				</WebPreviewNavigationButton>
				<div className="flex-1 flex items-center gap-2 px-2">
					<GlobeIcon size={14} className="text-muted-foreground shrink-0" />
					<WebPreviewUrl className="flex-1" />
				</div>
				<WebPreviewNavigationButton
					tooltip="Open in new tab"
					onClick={handleOpenInNewTab}
				>
					<ExternalLinkIcon size={16} />
				</WebPreviewNavigationButton>
				{onClose && (
					<WebPreviewNavigationButton tooltip="Close" onClick={onClose}>
						<XIcon size={16} />
					</WebPreviewNavigationButton>
				)}
			</WebPreviewNavigation>

			{hasError ? (
				<div className="flex-1 flex flex-col items-center justify-center gap-4 p-8 text-center">
					<p className="text-sm text-muted-foreground">
						Unable to load preview. The site may block iframe embedding.
					</p>
					<Button variant="outline" size="sm" onClick={handleOpenInNewTab}>
						<ExternalLinkIcon size={14} className="mr-2" />
						Open in new tab
					</Button>
				</div>
			) : (
				<div className="relative flex-1 flex">
					<WebPreviewBody
						key={key}
						onLoad={handleIframeLoad}
						onError={handleIframeError}
					/>
					{isLoading && (
						<div className="absolute inset-0 flex items-center justify-center bg-background/80">
							<RefreshCwIcon size={24} className="animate-spin text-muted-foreground" />
						</div>
					)}
				</div>
			)}

			{preview.title && (
				<div className="border-t px-4 py-2 text-xs text-muted-foreground truncate">
					{preview.title}
				</div>
			)}
		</WebPreview>
	);
}

export default WebPreviewRenderer;
