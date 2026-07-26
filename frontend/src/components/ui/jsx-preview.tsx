/**
 * JSX Preview component for rendering AI-generated React/JSX code.
 *
 * Supports:
 * - Dynamic JSX rendering via react-jsx-parser
 * - Streaming with auto-completion of unclosed tags
 * - Recharts components for data visualization
 * - shadcn/ui components (Cards, Badges, Alerts, Tables, Tabs, etc.)
 * - Lucide icons for visual communication
 * - Export to PNG/SVG
 */

import {
	createContext,
	useContext,
	useState,
	useCallback,
	useRef,
	useMemo,
	type ReactNode,
	type ComponentType,
} from 'react';
import { toast } from 'sonner';
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

// shadcn/ui components
import { Button } from '@/components/ui/button';
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert';
import { Separator } from '@/components/ui/separator';
import { Progress } from '@/components/ui/progress';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Accordion, AccordionItem, AccordionTrigger, AccordionContent } from '@/components/ui/accordion';
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell, TableCaption } from '@/components/ui/table';
import { Avatar, AvatarImage, AvatarFallback } from '@/components/ui/avatar';
import { Skeleton } from '@/components/ui/skeleton';

// Lucide icons - comprehensive set for AI chat context
import {
	// Status & Feedback
	CheckCircle, XCircle, AlertTriangle, AlertCircle, Info, HelpCircle, Loader2,
	// Trends & Analytics
	TrendingUp, TrendingDown, ArrowUp, ArrowDown, Activity, BarChart3,
	// Business & Finance
	DollarSign, ShoppingCart, CreditCard, Receipt, PieChart as PieChartIcon,
	// Actions
	Copy, Download, ExternalLink, Share2, Save, Trash2, Edit, Plus, Minus, X,
	// Navigation
	ChevronRight, ChevronDown, ChevronLeft, ChevronUp, ArrowRight, ArrowLeft,
	// Media
	Image as ImageIcon, Video, Music, FileText, File, FileIcon,
	// Communication
	Mail, MessageCircle, Phone, Calendar, Clock, Bell,
	// Users & Social
	User, Users, UserPlus, Heart, Star, ThumbsUp, ThumbsDown,
	// Tech
	Code, Terminal, Database, Cloud, Server, Wifi, Lock, Unlock, Key,
	// General
	Home, Settings, Search, Filter, Menu, MoreVertical, MoreHorizontal,
	Eye, EyeOff, Zap, Target, Flag, Bookmark, Tag,
} from 'lucide-react';

import { cn } from '@/lib/utils';
import { extractJsxAndBindings } from '@/utils/jsxPreambleParser';
import { fixCommonJsxMistakes } from '@/utils/jsxPostProcessor';

// Loose component type for the AI-generated JSX registry: props are supplied
// dynamically at runtime, so precise prop typing is not feasible here.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyComponent = ComponentType<any>;

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
const availableComponents: Record<string, AnyComponent> = {
	// Recharts - cast through unknown to avoid type issues with required props
	LineChart: LineChart as unknown as AnyComponent,
	Line: Line as unknown as AnyComponent,
	BarChart: BarChart as unknown as AnyComponent,
	Bar: Bar as unknown as AnyComponent,
	PieChart: PieChart as unknown as AnyComponent,
	Pie: Pie as unknown as AnyComponent,
	Cell: Cell as unknown as AnyComponent,
	AreaChart: AreaChart as unknown as AnyComponent,
	Area: Area as unknown as AnyComponent,
	XAxis: XAxis as unknown as AnyComponent,
	YAxis: YAxis as unknown as AnyComponent,
	CartesianGrid: CartesianGrid as unknown as AnyComponent,
	Tooltip: Tooltip as unknown as AnyComponent,
	Legend: Legend as unknown as AnyComponent,
	ResponsiveContainer: ResponsiveContainer as unknown as AnyComponent,
	ScatterChart: ScatterChart as unknown as AnyComponent,
	Scatter: Scatter as unknown as AnyComponent,
	RadarChart: RadarChart as unknown as AnyComponent,
	Radar: Radar as unknown as AnyComponent,
	PolarGrid: PolarGrid as unknown as AnyComponent,
	PolarAngleAxis: PolarAngleAxis as unknown as AnyComponent,
	PolarRadiusAxis: PolarRadiusAxis as unknown as AnyComponent,
	ComposedChart: ComposedChart as unknown as AnyComponent,
	Treemap: Treemap as unknown as AnyComponent,
	Funnel: Funnel as unknown as AnyComponent,
	FunnelChart: FunnelChart as unknown as AnyComponent,
	
	// shadcn/ui Components - Phase 1 & 2
	Button: Button as unknown as AnyComponent,
	Card: Card as unknown as AnyComponent,
	CardHeader: CardHeader as unknown as AnyComponent,
	CardTitle: CardTitle as unknown as AnyComponent,
	CardDescription: CardDescription as unknown as AnyComponent,
	CardContent: CardContent as unknown as AnyComponent,
	CardFooter: CardFooter as unknown as AnyComponent,
	Badge: Badge as unknown as AnyComponent,
	Alert: Alert as unknown as AnyComponent,
	AlertTitle: AlertTitle as unknown as AnyComponent,
	AlertDescription: AlertDescription as unknown as AnyComponent,
	Separator: Separator as unknown as AnyComponent,
	Progress: Progress as unknown as AnyComponent,
	Tabs: Tabs as unknown as AnyComponent,
	TabsList: TabsList as unknown as AnyComponent,
	TabsTrigger: TabsTrigger as unknown as AnyComponent,
	TabsContent: TabsContent as unknown as AnyComponent,
	Accordion: Accordion as unknown as AnyComponent,
	AccordionItem: AccordionItem as unknown as AnyComponent,
	AccordionTrigger: AccordionTrigger as unknown as AnyComponent,
	AccordionContent: AccordionContent as unknown as AnyComponent,
	Table: Table as unknown as AnyComponent,
	TableHeader: TableHeader as unknown as AnyComponent,
	TableBody: TableBody as unknown as AnyComponent,
	TableRow: TableRow as unknown as AnyComponent,
	TableHead: TableHead as unknown as AnyComponent,
	TableCell: TableCell as unknown as AnyComponent,
	TableCaption: TableCaption as unknown as AnyComponent,
	Avatar: Avatar as unknown as AnyComponent,
	AvatarImage: AvatarImage as unknown as AnyComponent,
	AvatarFallback: AvatarFallback as unknown as AnyComponent,
	Skeleton: Skeleton as unknown as AnyComponent,
	
	// Lucide Icons - Comprehensive Set
	// Status & Feedback
	CheckCircle: CheckCircle as unknown as AnyComponent,
	XCircle: XCircle as unknown as AnyComponent,
	AlertTriangle: AlertTriangle as unknown as AnyComponent,
	AlertCircle: AlertCircle as unknown as AnyComponent,
	Info: Info as unknown as AnyComponent,
	HelpCircle: HelpCircle as unknown as AnyComponent,
	Loader2: Loader2 as unknown as AnyComponent,
	// Trends & Analytics
	TrendingUp: TrendingUp as unknown as AnyComponent,
	TrendingDown: TrendingDown as unknown as AnyComponent,
	ArrowUp: ArrowUp as unknown as AnyComponent,
	ArrowDown: ArrowDown as unknown as AnyComponent,
	Activity: Activity as unknown as AnyComponent,
	BarChart3: BarChart3 as unknown as AnyComponent,
	// Business & Finance
	DollarSign: DollarSign as unknown as AnyComponent,
	ShoppingCart: ShoppingCart as unknown as AnyComponent,
	CreditCard: CreditCard as unknown as AnyComponent,
	Receipt: Receipt as unknown as AnyComponent,
	PieChartIcon: PieChartIcon as unknown as AnyComponent,
	// Actions
	Copy: Copy as unknown as AnyComponent,
	Download: Download as unknown as AnyComponent,
	ExternalLink: ExternalLink as unknown as AnyComponent,
	Share2: Share2 as unknown as AnyComponent,
	Save: Save as unknown as AnyComponent,
	Trash2: Trash2 as unknown as AnyComponent,
	Edit: Edit as unknown as AnyComponent,
	Plus: Plus as unknown as AnyComponent,
	Minus: Minus as unknown as AnyComponent,
	X: X as unknown as AnyComponent,
	// Navigation
	ChevronRight: ChevronRight as unknown as AnyComponent,
	ChevronDown: ChevronDown as unknown as AnyComponent,
	ChevronLeft: ChevronLeft as unknown as AnyComponent,
	ChevronUp: ChevronUp as unknown as AnyComponent,
	ArrowRight: ArrowRight as unknown as AnyComponent,
	ArrowLeft: ArrowLeft as unknown as AnyComponent,
	// Media
	ImageIcon: ImageIcon as unknown as AnyComponent,
	Video: Video as unknown as AnyComponent,
	Music: Music as unknown as AnyComponent,
	FileText: FileText as unknown as AnyComponent,
	File: File as unknown as AnyComponent,
	FileIcon: FileIcon as unknown as AnyComponent,
	// Communication
	Mail: Mail as unknown as AnyComponent,
	MessageCircle: MessageCircle as unknown as AnyComponent,
	Phone: Phone as unknown as AnyComponent,
	Calendar: Calendar as unknown as AnyComponent,
	Clock: Clock as unknown as AnyComponent,
	Bell: Bell as unknown as AnyComponent,
	// Users & Social
	User: User as unknown as AnyComponent,
	Users: Users as unknown as AnyComponent,
	UserPlus: UserPlus as unknown as AnyComponent,
	Heart: Heart as unknown as AnyComponent,
	Star: Star as unknown as AnyComponent,
	ThumbsUp: ThumbsUp as unknown as AnyComponent,
	ThumbsDown: ThumbsDown as unknown as AnyComponent,
	// Tech
	Code: Code as unknown as AnyComponent,
	Terminal: Terminal as unknown as AnyComponent,
	Database: Database as unknown as AnyComponent,
	Cloud: Cloud as unknown as AnyComponent,
	Server: Server as unknown as AnyComponent,
	Wifi: Wifi as unknown as AnyComponent,
	Lock: Lock as unknown as AnyComponent,
	Unlock: Unlock as unknown as AnyComponent,
	Key: Key as unknown as AnyComponent,
	// General
	Home: Home as unknown as AnyComponent,
	Settings: Settings as unknown as AnyComponent,
	Search: Search as unknown as AnyComponent,
	Filter: Filter as unknown as AnyComponent,
	Menu: Menu as unknown as AnyComponent,
	MoreVertical: MoreVertical as unknown as AnyComponent,
	MoreHorizontal: MoreHorizontal as unknown as AnyComponent,
	Eye: Eye as unknown as AnyComponent,
	EyeOff: EyeOff as unknown as AnyComponent,
	Zap: Zap as unknown as AnyComponent,
	Target: Target as unknown as AnyComponent,
	Flag: Flag as unknown as AnyComponent,
	Bookmark: Bookmark as unknown as AnyComponent,
	Tag: Tag as unknown as AnyComponent,
	
	// Basic HTML-like components
	Fragment: ({ children }: { children: ReactNode }) => <>{children}</>,
	div: (({ children, ...props }) => <div {...props}>{children}</div>) as AnyComponent,
	span: (({ children, ...props }) => <span {...props}>{children}</span>) as AnyComponent,
	p: (({ children, ...props }) => <p {...props}>{children}</p>) as AnyComponent,
};

// Default bindings available in JSX
const defaultBindings = {
	COLORS: CHART_COLORS,
	
	// JavaScript built-ins
	Math,
	JSON,
	Array,
	Object,
	console,
	
	// Number Formatting
	formatNumber: (n: number) => new Intl.NumberFormat().format(n),
	formatCurrency: (n: number, currency = 'USD') => 
		new Intl.NumberFormat('en-US', { style: 'currency', currency }).format(n),
	formatPercent: (n: number, decimals = 1) => 
		`${(n * 100).toFixed(decimals)}%`,
	formatCompact: (n: number) => 
		new Intl.NumberFormat('en-US', { notation: 'compact' }).format(n),
	
	// Date Formatting
	formatDate: (date: string | Date) => new Date(date).toLocaleDateString(),
	formatDateTime: (date: string | Date) => new Date(date).toLocaleString(),
	formatRelative: (date: string | Date) => {
		const diff = Date.now() - new Date(date).getTime();
		const days = Math.floor(diff / (1000 * 60 * 60 * 24));
		if (days === 0) return 'Today';
		if (days === 1) return 'Yesterday';
		if (days < 7) return `${days} days ago`;
		if (days < 30) return `${Math.floor(days / 7)} weeks ago`;
		return `${Math.floor(days / 30)} months ago`;
	},
	
	// String Helpers
	capitalize: (s: string) => s.charAt(0).toUpperCase() + s.slice(1),
	truncate: (s: string, length: number) => 
		s.length > length ? s.slice(0, length) + '...' : s,
	slugify: (s: string) => 
		s.toLowerCase().replace(/[^\w\s-]/g, '').replace(/\s+/g, '-'),
	
	// Array Helpers
	sum: (arr: number[]) => arr.reduce((a, b) => a + b, 0),
	avg: (arr: number[]) => arr.reduce((a, b) => a + b, 0) / arr.length,
	max: (arr: number[]) => Math.max(...arr),
	min: (arr: number[]) => Math.min(...arr),
	
	// Data Transformation
	groupBy: (arr: Record<string, unknown>[], key: string) =>
		arr.reduce((acc: Record<string, unknown[]>, item) => {
			const group = String(item[key]);
			acc[group] = acc[group] || [];
			acc[group].push(item);
			return acc;
		}, {} as Record<string, unknown[]>),
	sortBy: (arr: Record<string, unknown>[], key: string) =>
		[...arr].sort((a, b) => (a[key] as string | number) > (b[key] as string | number) ? 1 : -1),
};

export interface JSXPreviewProps {
	jsx: string;
	isStreaming?: boolean;
	components?: Record<string, AnyComponent>;
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
					'jsx-preview relative rounded-lg border p-4',
					className
				)}
				style={{ backgroundColor: '#ffffff' }}
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
	components?: Record<string, AnyComponent>;
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

	const { jsx: jsxBody, bindings: extractedBindings } = useMemo(
		() => extractJsxAndBindings(jsx),
		[jsx]
	);

	const fixedJsx = useMemo(() => fixCommonJsxMistakes(jsxBody), [jsxBody]);

	if (error) {
		return renderError ? (
			<>{renderError(error)}</>
		) : (
			<JSXPreviewError />
		);
	}

	// Process JSX for streaming (after preamble extraction and syntax fixes)
	const processedJsx = isStreaming ? autoCompleteJsx(fixedJsx) : fixedJsx;

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
				bindings={{ ...defaultBindings, ...extractedBindings, ...bindings }}
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

function isInsideExportIgnore(node: Element): boolean {
	return Boolean(node.closest('[data-export-ignore="true"]'));
}

function getExportableSvg(container: HTMLElement): SVGElement | null {
	const rechartsSurface = container.querySelector('.recharts-surface');
	if (rechartsSurface instanceof SVGElement && !isInsideExportIgnore(rechartsSurface)) {
		return rechartsSurface;
	}

	const candidates = Array.from(container.querySelectorAll('svg')).filter(
		(svg) => !isInsideExportIgnore(svg)
	);

	if (candidates.length === 0) return null;

	return candidates.reduce((largest, svg) => {
		const largestArea = largest.clientWidth * largest.clientHeight;
		const svgArea = svg.clientWidth * svg.clientHeight;
		return svgArea > largestArea ? svg : largest;
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
			const { toPng } = await import('html-to-image');

			const dataUrl = await toPng(containerRef.current, {
				backgroundColor: '#ffffff',
				pixelRatio: 2,
				filter: (node) => {
					// Hide export buttons during capture
					if (node instanceof HTMLElement && node.dataset.exportIgnore === 'true') {
						return false;
					}
					return true;
				},
			});

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

		const sourceSvg = getExportableSvg(containerRef.current);
		if (!sourceSvg) {
			toast.warning('No chart SVG found to export');
			return;
		}

		const svg = sourceSvg.cloneNode(true) as SVGElement;

		if (!svg.getAttribute('width')) {
			svg.setAttribute('width', sourceSvg.clientWidth.toString());
		}
		if (!svg.getAttribute('height')) {
			svg.setAttribute('height', sourceSvg.clientHeight.toString());
		}

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
		<div className={cn('flex items-center gap-2', className)} data-export-ignore="true">
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
