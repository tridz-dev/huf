/**
 * Mermaid diagram renderer component.
 *
 * Renders mermaid diagram code into SVG visualizations.
 */

import { useEffect, useRef, useState, useId } from 'react';
import mermaid from 'mermaid';
import { cn } from '@/lib/utils';

// Initialize mermaid with secure settings
mermaid.initialize({
	startOnLoad: false,
	theme: 'neutral',
	securityLevel: 'strict',
	fontFamily: 'inherit',
});

interface MermaidProps {
	chart: string;
	className?: string;
}

export function Mermaid({ chart, className }: MermaidProps) {
	const containerRef = useRef<HTMLDivElement>(null);
	const [svg, setSvg] = useState<string>('');
	const [error, setError] = useState<string>('');
	const [isLoading, setIsLoading] = useState(true);
	const uniqueId = useId().replace(/:/g, '-');

	useEffect(() => {
		const render = async () => {
			if (!chart || !chart.trim()) {
				setError('No chart content provided');
				setIsLoading(false);
				return;
			}

			try {
				setIsLoading(true);
				setError('');

				// Generate a unique ID for this render
				const id = `mermaid-${uniqueId}-${Date.now()}`;

				// Render the mermaid diagram
				const { svg: renderedSvg } = await mermaid.render(id, chart.trim());
				setSvg(renderedSvg);
			} catch (e) {
				const errorMessage = e instanceof Error ? e.message : 'Failed to render diagram';
				setError(errorMessage);
				setSvg('');
			} finally {
				setIsLoading(false);
			}
		};

		render();
	}, [chart, uniqueId]);

	if (isLoading) {
		return (
			<div className={cn('flex items-center justify-center p-8 bg-muted/50 rounded border', className)}>
				<div className="animate-pulse text-muted-foreground">Rendering diagram...</div>
			</div>
		);
	}

	if (error) {
		return (
			<div className={cn('p-4 bg-destructive/10 border border-destructive/20 rounded', className)}>
				<p className="text-sm text-destructive font-medium">Failed to render Mermaid diagram</p>
				<p className="text-xs text-destructive/80 mt-1">{error}</p>
			</div>
		);
	}

	return (
		<div
			ref={containerRef}
			className={cn('flex items-center justify-center overflow-auto bg-white rounded border p-4', className)}
			// biome-ignore lint/security/noDangerouslySetInnerHtml: Mermaid SVG output is sanitized by mermaid.js
			dangerouslySetInnerHTML={{ __html: svg }}
		/>
	);
}

export default Mermaid;
