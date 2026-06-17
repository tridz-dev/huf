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
	
	// shadcn/ui Components - Phase 1 & 2
	Button: Button as unknown as ComponentType<any>,
	Card: Card as unknown as ComponentType<any>,
	CardHeader: CardHeader as unknown as ComponentType<any>,
	CardTitle: CardTitle as unknown as ComponentType<any>,
	CardDescription: CardDescription as unknown as ComponentType<any>,
	CardContent: CardContent as unknown as ComponentType<any>,
	CardFooter: CardFooter as unknown as ComponentType<any>,
	Badge: Badge as unknown as ComponentType<any>,
	Alert: Alert as unknown as ComponentType<any>,
	AlertTitle: AlertTitle as unknown as ComponentType<any>,
	AlertDescription: AlertDescription as unknown as ComponentType<any>,
	Separator: Separator as unknown as ComponentType<any>,
	Progress: Progress as unknown as ComponentType<any>,
	Tabs: Tabs as unknown as ComponentType<any>,
	TabsList: TabsList as unknown as ComponentType<any>,
	TabsTrigger: TabsTrigger as unknown as ComponentType<any>,
	TabsContent: TabsContent as unknown as ComponentType<any>,
	Accordion: Accordion as unknown as ComponentType<any>,
	AccordionItem: AccordionItem as unknown as ComponentType<any>,
	AccordionTrigger: AccordionTrigger as unknown as ComponentType<any>,
	AccordionContent: AccordionContent as unknown as ComponentType<any>,
	Table: Table as unknown as ComponentType<any>,
	TableHeader: TableHeader as unknown as ComponentType<any>,
	TableBody: TableBody as unknown as ComponentType<any>,
	TableRow: TableRow as unknown as ComponentType<any>,
	TableHead: TableHead as unknown as ComponentType<any>,
	TableCell: TableCell as unknown as ComponentType<any>,
	TableCaption: TableCaption as unknown as ComponentType<any>,
	Avatar: Avatar as unknown as ComponentType<any>,
	AvatarImage: AvatarImage as unknown as ComponentType<any>,
	AvatarFallback: AvatarFallback as unknown as ComponentType<any>,
	Skeleton: Skeleton as unknown as ComponentType<any>,
	
	// Lucide Icons - Comprehensive Set
	// Status & Feedback
	CheckCircle: CheckCircle as unknown as ComponentType<any>,
	XCircle: XCircle as unknown as ComponentType<any>,
	AlertTriangle: AlertTriangle as unknown as ComponentType<any>,
	AlertCircle: AlertCircle as unknown as ComponentType<any>,
	Info: Info as unknown as ComponentType<any>,
	HelpCircle: HelpCircle as unknown as ComponentType<any>,
	Loader2: Loader2 as unknown as ComponentType<any>,
	// Trends & Analytics
	TrendingUp: TrendingUp as unknown as ComponentType<any>,
	TrendingDown: TrendingDown as unknown as ComponentType<any>,
	ArrowUp: ArrowUp as unknown as ComponentType<any>,
	ArrowDown: ArrowDown as unknown as ComponentType<any>,
	Activity: Activity as unknown as ComponentType<any>,
	BarChart3: BarChart3 as unknown as ComponentType<any>,
	// Business & Finance
	DollarSign: DollarSign as unknown as ComponentType<any>,
	ShoppingCart: ShoppingCart as unknown as ComponentType<any>,
	CreditCard: CreditCard as unknown as ComponentType<any>,
	Receipt: Receipt as unknown as ComponentType<any>,
	PieChartIcon: PieChartIcon as unknown as ComponentType<any>,
	// Actions
	Copy: Copy as unknown as ComponentType<any>,
	Download: Download as unknown as ComponentType<any>,
	ExternalLink: ExternalLink as unknown as ComponentType<any>,
	Share2: Share2 as unknown as ComponentType<any>,
	Save: Save as unknown as ComponentType<any>,
	Trash2: Trash2 as unknown as ComponentType<any>,
	Edit: Edit as unknown as ComponentType<any>,
	Plus: Plus as unknown as ComponentType<any>,
	Minus: Minus as unknown as ComponentType<any>,
	X: X as unknown as ComponentType<any>,
	// Navigation
	ChevronRight: ChevronRight as unknown as ComponentType<any>,
	ChevronDown: ChevronDown as unknown as ComponentType<any>,
	ChevronLeft: ChevronLeft as unknown as ComponentType<any>,
	ChevronUp: ChevronUp as unknown as ComponentType<any>,
	ArrowRight: ArrowRight as unknown as ComponentType<any>,
	ArrowLeft: ArrowLeft as unknown as ComponentType<any>,
	// Media
	ImageIcon: ImageIcon as unknown as ComponentType<any>,
	Video: Video as unknown as ComponentType<any>,
	Music: Music as unknown as ComponentType<any>,
	FileText: FileText as unknown as ComponentType<any>,
	File: File as unknown as ComponentType<any>,
	FileIcon: FileIcon as unknown as ComponentType<any>,
	// Communication
	Mail: Mail as unknown as ComponentType<any>,
	MessageCircle: MessageCircle as unknown as ComponentType<any>,
	Phone: Phone as unknown as ComponentType<any>,
	Calendar: Calendar as unknown as ComponentType<any>,
	Clock: Clock as unknown as ComponentType<any>,
	Bell: Bell as unknown as ComponentType<any>,
	// Users & Social
	User: User as unknown as ComponentType<any>,
	Users: Users as unknown as ComponentType<any>,
	UserPlus: UserPlus as unknown as ComponentType<any>,
	Heart: Heart as unknown as ComponentType<any>,
	Star: Star as unknown as ComponentType<any>,
	ThumbsUp: ThumbsUp as unknown as ComponentType<any>,
	ThumbsDown: ThumbsDown as unknown as ComponentType<any>,
	// Tech
	Code: Code as unknown as ComponentType<any>,
	Terminal: Terminal as unknown as ComponentType<any>,
	Database: Database as unknown as ComponentType<any>,
	Cloud: Cloud as unknown as ComponentType<any>,
	Server: Server as unknown as ComponentType<any>,
	Wifi: Wifi as unknown as ComponentType<any>,
	Lock: Lock as unknown as ComponentType<any>,
	Unlock: Unlock as unknown as ComponentType<any>,
	Key: Key as unknown as ComponentType<any>,
	// General
	Home: Home as unknown as ComponentType<any>,
	Settings: Settings as unknown as ComponentType<any>,
	Search: Search as unknown as ComponentType<any>,
	Filter: Filter as unknown as ComponentType<any>,
	Menu: Menu as unknown as ComponentType<any>,
	MoreVertical: MoreVertical as unknown as ComponentType<any>,
	MoreHorizontal: MoreHorizontal as unknown as ComponentType<any>,
	Eye: Eye as unknown as ComponentType<any>,
	EyeOff: EyeOff as unknown as ComponentType<any>,
	Zap: Zap as unknown as ComponentType<any>,
	Target: Target as unknown as ComponentType<any>,
	Flag: Flag as unknown as ComponentType<any>,
	Bookmark: Bookmark as unknown as ComponentType<any>,
	Tag: Tag as unknown as ComponentType<any>,
	
	// Basic HTML-like components
	Fragment: ({ children }: { children: ReactNode }) => <>{children}</>,
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
	groupBy: (arr: any[], key: string) => 
		arr.reduce((acc, item) => {
			const group = item[key];
			acc[group] = acc[group] || [];
			acc[group].push(item);
			return acc;
		}, {}),
	sortBy: (arr: any[], key: string) => 
		[...arr].sort((a, b) => a[key] > b[key] ? 1 : -1),
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
