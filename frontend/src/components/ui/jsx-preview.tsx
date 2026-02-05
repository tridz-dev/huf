/**
 * JSX Preview component for rendering AI-generated React/JSX code.
 *
 * Supports:
 * - Dynamic JSX rendering via react-jsx-parser
 * - Streaming with auto-completion of unclosed tags
 * - Recharts components for data visualization
 * - Export to PNG/SVG
 */

import {
	createContext,
	useContext,
	useState,
	useCallback,
	useRef,
	type ReactNode,
	type ComponentType,
} from 'react';
import JsxParser from 'react-jsx-parser';

// Recharts components for chart rendering
import {
	LineChart,
	Line,
	BarChart,
	Bar,
	PieChart,
	Pie,
	Cell,
	AreaChart,
	Area,
	XAxis,
	YAxis,
	CartesianGrid,
	Tooltip,
	Legend,
	ResponsiveContainer,
	ScatterChart,
	Scatter,
	RadarChart,
	Radar,
	PolarGrid,
	PolarAngleAxis,
	PolarRadiusAxis,
	ComposedChart,
	Treemap,
	Funnel,
	FunnelChart,
} from 'recharts';

import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { ImageIcon, FileIcon } from 'lucide-react';

// Common colors for charts
const CHART_COLORS = [
	'#8884d8',
	'#82ca9d',
	'#ffc658',
	'#ff7300',
	'#00C49F',
	'#FFBB28',
	'#FF8042',
	'#0088FE',
	'#00C49F',
	'#FFBB28',
];

// Context for JSX Preview
interface JSXPreviewContextValue {
	jsx: string;
	isStreaming: boolean;
	error: Error | null;
	setError: (error: Error | null) => void;
	containerRef: React.RefObject<HTMLDivElement>;
}

const JSXPreviewContext = createContext<JSXPreviewContextValue | null>(null);

const useJSXPreview = () => {
	const context = useContext(JSXPreviewContext);
	if (!context) {
		throw new Error('JSXPreview components must be used within JSXPreview');
	}
	return context;
};

// Auto-complete unclosed tags for streaming
function autoCompleteJsx(jsx: string): string {
	if (!jsx) return '';

	// Track open tags
	const tagStack: string[] = [];
	const tagRegex = /<\/?([a-zA-Z][a-zA-Z0-9]*)[^>]*\/?>/g;
	let match;

	while ((match = tagRegex.exec(jsx)) !== null) {
		const [fullMatch, tagName] = match;
		const isSelfClosing = fullMatch.endsWith('/>');
		const isClosing = fullMatch.startsWith('</');

		if (isClosing) {
			// Pop from stack if matching
			const lastTag = tagStack[tagStack.length - 1];
			if (lastTag === tagName) {
				tagStack.pop();
			}
		} else if (!isSelfClosing) {
			tagStack.push(tagName);
		}
	}

	// Close any unclosed tags
	let completed = jsx;
	while (tagStack.length > 0) {
		const tag = tagStack.pop();
		completed += `</${tag}>`;
	}

	return completed;
}

// Available components for JSX parsing - cast through unknown to avoid strict type checking
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const availableComponents: Record<string, ComponentType<any>> = {
	// Recharts - cast through unknown to avoid type issues with required props
	LineChart: LineChart as unknown as ComponentType<any>,
	Line: Line as unknown as ComponentType<any>,
	BarChart: BarChart as unknown as ComponentType<any>,
	Bar: Bar as unknown as ComponentType<any>,
	PieChart: PieChart as unknown as ComponentType<any>,
	Pie: Pie as unknown as ComponentType<any>,
	Cell: Cell as unknown as ComponentType<any>,
	AreaChart: AreaChart as unknown as ComponentType<any>,
	Area: Area as unknown as ComponentType<any>,
	XAxis: XAxis as unknown as ComponentType<any>,
	YAxis: YAxis as unknown as ComponentType<any>,
	CartesianGrid: CartesianGrid as unknown as ComponentType<any>,
	Tooltip: Tooltip as unknown as ComponentType<any>,
	Legend: Legend as unknown as ComponentType<any>,
	ResponsiveContainer: ResponsiveContainer as unknown as ComponentType<any>,
	ScatterChart: ScatterChart as unknown as ComponentType<any>,
	Scatter: Scatter as unknown as ComponentType<any>,
	RadarChart: RadarChart as unknown as ComponentType<any>,
	Radar: Radar as unknown as ComponentType<any>,
	PolarGrid: PolarGrid as unknown as ComponentType<any>,
	PolarAngleAxis: PolarAngleAxis as unknown as ComponentType<any>,
	PolarRadiusAxis: PolarRadiusAxis as unknown as ComponentType<any>,
	ComposedChart: ComposedChart as unknown as ComponentType<any>,
	Treemap: Treemap as unknown as ComponentType<any>,
	Funnel: Funnel as unknown as ComponentType<any>,
	FunnelChart: FunnelChart as unknown as ComponentType<any>,
	// Basic HTML-like components
	Fragment: ({ children }: { children: ReactNode }) => <>{children}</>,
};

// Default bindings available in JSX
const defaultBindings = {
	COLORS: CHART_COLORS,
	// Common data transformation helpers
	Math,
	JSON,
	Array,
	Object,
	console,
};

export interface JSXPreviewProps {
	jsx: string;
	isStreaming?: boolean;
	components?: Record<string, ComponentType<any>>;
	bindings?: Record<string, unknown>;
	className?: string;
	children?: ReactNode;
	onError?: (error: Error) => void;
}

export function JSXPreview({
	jsx,
	isStreaming = false,
	components = {},
	bindings = {},
	className,
	children,
	onError,
}: JSXPreviewProps) {
	const [error, setErrorState] = useState<Error | null>(null);
	const containerRef = useRef<HTMLDivElement>(null);

	const setError = useCallback(
		(err: Error | null) => {
			setErrorState(err);
			if (err) {
				onError?.(err);
			}
		},
		[onError]
	);

	const contextValue: JSXPreviewContextValue = {
		jsx,
		isStreaming,
		error,
		setError,
		containerRef,
	};

	return (
		<JSXPreviewContext.Provider value={contextValue}>
			<div
				ref={containerRef}
				className={cn(
					'jsx-preview relative rounded-lg border bg-white p-4',
					className
				)}
			>
				{children || (
					<>
						<JSXPreviewContent
							components={components}
							bindings={bindings}
						/>
						<JSXPreviewError />
					</>
				)}
			</div>
		</JSXPreviewContext.Provider>
	);
}

export interface JSXPreviewContentProps {
	components?: Record<string, ComponentType<any>>;
	bindings?: Record<string, unknown>;
	className?: string;
	renderError?: (error: Error) => ReactNode;
}

export function JSXPreviewContent({
	components = {},
	bindings = {},
	className,
	renderError,
}: JSXPreviewContentProps) {
	const { jsx, isStreaming, error, setError } = useJSXPreview();

	if (error) {
		return renderError ? (
			<>{renderError(error)}</>
		) : (
			<JSXPreviewError />
		);
	}

	// Process JSX for streaming
	const processedJsx = isStreaming ? autoCompleteJsx(jsx) : jsx;

	if (!processedJsx || !processedJsx.trim()) {
		return (
			<div className={cn('text-muted-foreground text-sm', className)}>
				No JSX content to render
			</div>
		);
	}

	return (
		<div className={cn('jsx-preview-content', className)}>
			<JsxParser
				jsx={processedJsx}
				components={{ ...availableComponents, ...components }}
				bindings={{ ...defaultBindings, ...bindings }}
				renderError={(err) => {
					setError(new Error(err.error));
					return null;
				}}
				renderInWrapper={false}
				allowUnknownElements={false}
				autoCloseVoidElements
			/>
		</div>
	);
}

export interface JSXPreviewErrorProps {
	className?: string;
	children?: ReactNode;
}

export function JSXPreviewError({ className, children }: JSXPreviewErrorProps) {
	const { error } = useJSXPreview();

	if (!error) return null;

	return (
		<div
			className={cn(
				'rounded-md bg-destructive/10 p-4 text-sm text-destructive',
				className
			)}
		>
			{children || (
				<>
					<p className="font-medium">Failed to render JSX</p>
					<p className="mt-1 text-xs opacity-80">{error.message}</p>
				</>
			)}
		</div>
	);
}

export interface JSXPreviewExportProps {
	className?: string;
	filename?: string;
}

/**
 * Inline computed styles on an SVG element and all its descendants.
 * Resolves modern CSS (oklch, etc.) to rgb via getComputedStyle.
 */
function inlineSvgStyles(original: Element, clone: Element): void {
	const computed = window.getComputedStyle(original);
	const el = clone as SVGElement & { style: CSSStyleDeclaration };
	const props = ['fill', 'stroke', 'stroke-width', 'font-family', 'font-size', 'font-weight', 'opacity', 'color', 'text-anchor', 'dominant-baseline'];
	props.forEach((prop) => {
		const val = computed.getPropertyValue(prop);
		if (val) el.style?.setProperty(prop, val);
	});
	const origChildren = original.children;
	const cloneChildren = clone.children;
	for (let i = 0; i < origChildren.length && i < cloneChildren.length; i++) {
		inlineSvgStyles(origChildren[i], cloneChildren[i]);
	}
}

/**
 * Read legend items from Recharts' HTML legend and return structured data.
 */
function extractLegendItems(container: HTMLElement): Array<{ color: string; label: string }> {
	const items: Array<{ color: string; label: string }> = [];
	// Recharts renders legend items as <li> elements with an <svg> icon and text
	const legendItems = container.querySelectorAll('.recharts-legend-item');
	legendItems.forEach((li) => {
		const svg = li.querySelector('svg');
		const surface = svg?.querySelector('path, rect, circle, line');
		const color = surface
			? window.getComputedStyle(surface).fill || surface.getAttribute('fill') || '#888'
			: '#888';
		const textEl = li.querySelector('.recharts-legend-item-text');
		const label = textEl?.textContent?.trim() || '';
		if (label) items.push({ color, label });
	});
	return items;
}

/**
 * Append legend items as native SVG elements below the chart.
 * Returns the extra height added for the legend row.
 */
function appendLegendToSvg(
	svg: SVGElement,
	items: Array<{ color: string; label: string }>,
	chartWidth: number,
	yOffset: number,
): number {
	if (items.length === 0) return 0;

	const ns = 'http://www.w3.org/2000/svg';
	const legendGroup = document.createElementNS(ns, 'g');
	legendGroup.setAttribute('class', 'exported-legend');

	const boxSize = 10;
	const gap = 8;
	const itemGap = 20;
	const fontSize = 12;

	// Measure total width to center the legend row
	const canvas = document.createElement('canvas');
	const ctx = canvas.getContext('2d');
	ctx!.font = `${fontSize}px sans-serif`;

	let totalWidth = 0;
	const widths = items.map((item) => {
		const textWidth = ctx!.measureText(item.label).width;
		return boxSize + gap + textWidth;
	});
	totalWidth = widths.reduce((sum, w) => sum + w, 0) + itemGap * (items.length - 1);

	let x = (chartWidth - totalWidth) / 2;
	const y = yOffset + 8;

	items.forEach((item, i) => {
		// Color box
		const rect = document.createElementNS(ns, 'rect');
		rect.setAttribute('x', String(x));
		rect.setAttribute('y', String(y));
		rect.setAttribute('width', String(boxSize));
		rect.setAttribute('height', String(boxSize));
		rect.setAttribute('fill', item.color);
		rect.setAttribute('rx', '2');
		legendGroup.appendChild(rect);

		// Label text
		const text = document.createElementNS(ns, 'text');
		text.setAttribute('x', String(x + boxSize + gap));
		text.setAttribute('y', String(y + boxSize - 1));
		text.setAttribute('font-size', String(fontSize));
		text.setAttribute('font-family', 'sans-serif');
		text.setAttribute('fill', '#333');
		text.textContent = item.label;
		legendGroup.appendChild(text);

		x += widths[i] + itemGap;
	});

	svg.appendChild(legendGroup);
	return boxSize + 20; // legend row height
}

/**
 * Convert an SVG element to PNG, including Recharts legend items
 * that are rendered as HTML outside the SVG.
 */
function svgWithLegendToPng(
	svgElement: SVGElement,
	container: HTMLElement,
	scale = 2,
): Promise<string> {
	return new Promise((resolve, reject) => {
		const svg = svgElement.cloneNode(true) as SVGElement;

		const width = svgElement.clientWidth || svgElement.getBoundingClientRect().width;
		let height = svgElement.clientHeight || svgElement.getBoundingClientRect().height;
		svg.setAttribute('width', String(width));
		svg.setAttribute('height', String(height));

		// Inline computed styles (resolves oklch → rgb)
		inlineSvgStyles(svgElement, svg);

		// Extract legend items from the HTML and inject into SVG
		const legendItems = extractLegendItems(container);
		const legendHeight = appendLegendToSvg(svg, legendItems, width, height);
		height += legendHeight;
		svg.setAttribute('height', String(height));
		// Update viewBox if present
		const vb = svgElement.getAttribute('viewBox');
		if (vb) {
			const parts = vb.split(/\s+|,/);
			if (parts.length === 4) {
				svg.setAttribute('viewBox', `${parts[0]} ${parts[1]} ${parts[2]} ${height}`);
			}
		}

		const serializer = new XMLSerializer();
		const svgString = serializer.serializeToString(svg);
		const svgBlob = new Blob([svgString], { type: 'image/svg+xml;charset=utf-8' });
		const url = URL.createObjectURL(svgBlob);

		const img = new window.Image();
		img.onload = () => {
			const canvas = document.createElement('canvas');
			canvas.width = width * scale;
			canvas.height = height * scale;
			const ctx = canvas.getContext('2d');
			if (!ctx) {
				URL.revokeObjectURL(url);
				reject(new Error('Could not get canvas context'));
				return;
			}
			ctx.fillStyle = '#ffffff';
			ctx.fillRect(0, 0, canvas.width, canvas.height);
			ctx.scale(scale, scale);
			ctx.drawImage(img, 0, 0);
			URL.revokeObjectURL(url);
			resolve(canvas.toDataURL('image/png'));
		};
		img.onerror = () => {
			URL.revokeObjectURL(url);
			reject(new Error('Failed to load SVG as image'));
		};
		img.src = url;
	});
}

export function JSXPreviewExport({
	className,
	filename = 'chart',
}: JSXPreviewExportProps) {
	const { containerRef } = useJSXPreview();
	const [isExporting, setIsExporting] = useState(false);

	const exportToPng = useCallback(async () => {
		if (!containerRef.current) return;

		setIsExporting(true);
		try {
			const container =
				containerRef.current.querySelector('.jsx-preview-content') as HTMLElement
				|| containerRef.current;

			// Find the largest SVG (the chart, not small icons)
			const svgElements = container.querySelectorAll('svg');
			if (svgElements.length === 0) {
				console.warn('No SVG elements found to export as PNG');
				return;
			}
			const svg = Array.from(svgElements).reduce((largest, el) =>
				el.getBoundingClientRect().width > largest.getBoundingClientRect().width ? el : largest
			);

			const dataUrl = await svgWithLegendToPng(svg, container);
			const link = document.createElement('a');
			link.download = `${filename}.png`;
			link.href = dataUrl;
			link.click();
		} catch (err) {
			console.error('Failed to export PNG:', err);
		} finally {
			setIsExporting(false);
		}
	}, [containerRef, filename]);

	const exportToSvg = useCallback(() => {
		if (!containerRef.current) return;

		// Find SVG elements in the container
		const svgElements = containerRef.current.querySelectorAll('svg');
		if (svgElements.length === 0) {
			console.warn('No SVG elements found to export');
			return;
		}

		// Clone the first SVG (usually the chart)
		const svg = svgElements[0].cloneNode(true) as SVGElement;

		// Set dimensions if not present
		if (!svg.getAttribute('width')) {
			svg.setAttribute('width', svgElements[0].clientWidth.toString());
		}
		if (!svg.getAttribute('height')) {
			svg.setAttribute('height', svgElements[0].clientHeight.toString());
		}

		// Serialize and download
		const serializer = new XMLSerializer();
		const svgString = serializer.serializeToString(svg);
		const blob = new Blob([svgString], { type: 'image/svg+xml' });
		const url = URL.createObjectURL(blob);

		const link = document.createElement('a');
		link.download = `${filename}.svg`;
		link.href = url;
		link.click();

		URL.revokeObjectURL(url);
	}, [containerRef, filename]);

	return (
		<div className={cn('flex items-center gap-2', className)}>
			<Button
				variant="outline"
				size="sm"
				onClick={exportToPng}
				disabled={isExporting}
			>
				<ImageIcon size={14} className="mr-1" />
				PNG
			</Button>
			<Button variant="outline" size="sm" onClick={exportToSvg}>
				<FileIcon size={14} className="mr-1" />
				SVG
			</Button>
		</div>
	);
}

export default JSXPreview;
