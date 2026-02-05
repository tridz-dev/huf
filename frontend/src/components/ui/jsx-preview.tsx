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
 * Inline all computed styles on an element and its descendants.
 * This ensures the exported image looks correct without external stylesheets.
 */
function inlineComputedStyles(original: Element, clone: Element): void {
	const computed = window.getComputedStyle(original);
	const cloneEl = clone as HTMLElement | SVGElement;

	// Inline key style properties that affect visual appearance
	const props = [
		'color', 'background-color', 'background',
		'font-family', 'font-size', 'font-weight', 'font-style',
		'text-align', 'text-decoration', 'line-height', 'letter-spacing',
		'fill', 'stroke', 'stroke-width', 'opacity',
		'border', 'border-radius', 'padding', 'margin',
		'display', 'flex-direction', 'align-items', 'justify-content', 'gap',
		'width', 'height', 'min-width', 'min-height',
		'overflow', 'white-space', 'list-style',
	];

	props.forEach((prop) => {
		const val = computed.getPropertyValue(prop);
		if (val && val !== '' && val !== 'none' && val !== 'normal' && val !== 'auto') {
			cloneEl.style?.setProperty(prop, val);
		}
	});

	// Recurse into children
	const originalChildren = original.children;
	const cloneChildren = clone.children;
	for (let i = 0; i < originalChildren.length && i < cloneChildren.length; i++) {
		inlineComputedStyles(originalChildren[i], cloneChildren[i]);
	}
}

/**
 * Export an HTML element (including SVG charts, legends, labels) to PNG
 * using foreignObject inside an SVG. This bypasses html2canvas and
 * avoids issues with modern CSS color functions like oklch().
 */
function elementToPng(element: HTMLElement, scale = 2): Promise<string> {
	return new Promise((resolve, reject) => {
		const rect = element.getBoundingClientRect();
		const width = rect.width;
		const height = rect.height;

		// Clone the element and inline all computed styles
		const clone = element.cloneNode(true) as HTMLElement;
		inlineComputedStyles(element, clone);

		// Reset position styles on the clone root
		clone.style.setProperty('margin', '0');
		clone.style.setProperty('position', 'static');

		// Serialize the clone to an XHTML string (required for foreignObject)
		const serializer = new XMLSerializer();
		const xhtml = serializer.serializeToString(clone);

		// Wrap in an SVG with foreignObject
		const svgString = `
			<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}">
				<foreignObject width="100%" height="100%">
					<div xmlns="http://www.w3.org/1999/xhtml"
						style="width:${width}px;height:${height}px;background:#fff;">
						${xhtml}
					</div>
				</foreignObject>
			</svg>
		`;

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
			reject(new Error('Failed to render element as image'));
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
			// Find the jsx-preview-content div which includes the chart + legend
			const contentEl =
				containerRef.current.querySelector('.jsx-preview-content') as HTMLElement
				|| containerRef.current;

			const dataUrl = await elementToPng(contentEl);
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
