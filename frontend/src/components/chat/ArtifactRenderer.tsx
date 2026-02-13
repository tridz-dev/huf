/**
 * Renderer component for AI-generated artifacts.
 *
 * This component takes a parsed artifact and renders it using the appropriate
 * visualization based on its type (code, html, svg, mermaid, etc.)
 */

import { useState, useCallback } from 'react';
import {
	Artifact,
	ArtifactHeader,
	ArtifactTitle,
	ArtifactDescription,
	ArtifactActions,
	ArtifactAction,
	ArtifactContent,
	ArtifactClose,
} from '@/components/ai-elements/artifact';
import { CodeBlock } from '@/components/ai-elements/code-block';
import { MessageResponse } from '@/components/ai-elements/message';
import {
	CopyIcon,
	DownloadIcon,
	MaximizeIcon,
	MinimizeIcon,
	CheckIcon,
	CodeIcon,
	FileTextIcon,
	ImageIcon,
	LayoutIcon,
	BarChartIcon,
	ExternalLinkIcon,
} from 'lucide-react';
import type { ParsedArtifact, ArtifactType } from '@/types/artifact.types';
import type { BundledLanguage } from 'shiki';
import { cn } from '@/lib/utils';
import { Mermaid } from '@/components/ui/mermaid';
import { JSXPreview, JSXPreviewContent, JSXPreviewExport } from '@/components/ui/jsx-preview';

interface ArtifactRendererProps {
	artifact: ParsedArtifact;
	onClose?: () => void;
	className?: string;
	/** Agent Message document name — enables "Open" for jsx/chart artifacts */
	messageId?: string;
}

// Map artifact types to icons
const ARTIFACT_ICONS: Record<ArtifactType, typeof CodeIcon> = {
	code: CodeIcon,
	document: FileTextIcon,
	html: LayoutIcon,
	svg: ImageIcon,
	mermaid: LayoutIcon,
	'react-component': CodeIcon,
	markdown: FileTextIcon,
	jsx: LayoutIcon,
	chart: BarChartIcon,
};

// Map common language aliases to Shiki language names
const LANGUAGE_MAP: Record<string, string> = {
	js: 'javascript',
	ts: 'typescript',
	py: 'python',
	rb: 'ruby',
	yml: 'yaml',
	sh: 'bash',
	shell: 'bash',
	zsh: 'bash',
	dockerfile: 'docker',
	md: 'markdown',
	txt: 'text',
	text: 'text',
};

function normalizeLanguage(language?: string): BundledLanguage {
	if (!language) return 'text' as BundledLanguage;
	const lower = language.toLowerCase();
	return (LANGUAGE_MAP[lower] || lower) as BundledLanguage;
}

export function ArtifactRenderer({
	artifact,
	onClose,
	className,
	messageId,
}: ArtifactRendererProps) {
	const [isFullscreen, setIsFullscreen] = useState(false);
	const [isCopied, setIsCopied] = useState(false);

	const handleCopy = useCallback(async () => {
		try {
			await navigator.clipboard.writeText(artifact.content);
			setIsCopied(true);
			setTimeout(() => setIsCopied(false), 2000);
		} catch (error) {
			console.error('Failed to copy:', error);
		}
	}, [artifact.content]);

	const handleDownload = useCallback(() => {
		const blob = new Blob([artifact.content], { type: 'text/plain' });
		const url = URL.createObjectURL(blob);
		const a = document.createElement('a');
		a.href = url;

		// Determine file extension based on type and language
		let extension = 'txt';
		if (artifact.type === 'code' && artifact.language) {
			const langMap: Record<string, string> = {
				javascript: 'js',
				typescript: 'ts',
				python: 'py',
				ruby: 'rb',
				rust: 'rs',
				golang: 'go',
				go: 'go',
				java: 'java',
				csharp: 'cs',
				cpp: 'cpp',
				c: 'c',
				html: 'html',
				css: 'css',
				json: 'json',
				yaml: 'yml',
				markdown: 'md',
				sql: 'sql',
				bash: 'sh',
				shell: 'sh',
			};
			extension = langMap[artifact.language.toLowerCase()] || artifact.language;
		} else if (artifact.type === 'html') {
			extension = 'html';
		} else if (artifact.type === 'svg') {
			extension = 'svg';
		} else if (artifact.type === 'mermaid') {
			extension = 'mmd';
		} else if (artifact.type === 'markdown' || artifact.type === 'document') {
			extension = 'md';
		} else if (artifact.type === 'jsx' || artifact.type === 'chart') {
			extension = 'jsx';
		}

		a.download = artifact.title
			? `${artifact.title.replace(/[^a-z0-9]/gi, '_')}.${extension}`
			: `artifact.${extension}`;
		a.click();
		URL.revokeObjectURL(url);
	}, [artifact]);

	const toggleFullscreen = useCallback(() => {
		setIsFullscreen((prev) => !prev);
	}, []);

	const handleOpenPreview = useCallback(() => {
		if (!messageId) return;
		window.open(`/huf/view/${messageId}`, '_blank', 'noopener');
	}, [messageId]);

	const renderContent = () => {
		switch (artifact.type) {
			case 'code':
			case 'react-component':
				return (
					<CodeBlock
						code={artifact.content}
						language={normalizeLanguage(artifact.language)}
						showLineNumbers
					/>
				);

			case 'html':
				return (
					<div className="flex flex-col gap-2">
						<iframe
							srcDoc={artifact.content}
							sandbox="allow-scripts"
							className="w-full h-96 border rounded bg-white"
							title={artifact.title || 'HTML Preview'}
						/>
						<details className="text-xs">
							<summary className="cursor-pointer text-muted-foreground hover:text-foreground">
								View Source
							</summary>
							<CodeBlock code={artifact.content} language="html" />
						</details>
					</div>
				);

			case 'svg':
				return (
					<div className="flex flex-col gap-2">
						<div
							className="flex items-center justify-center p-4 bg-white rounded border"
							// biome-ignore lint/security/noDangerouslySetInnerHtml: SVG rendering requires innerHTML
							dangerouslySetInnerHTML={{ __html: artifact.content }}
						/>
						<details className="text-xs">
							<summary className="cursor-pointer text-muted-foreground hover:text-foreground">
								View Source
							</summary>
							<CodeBlock code={artifact.content} language="xml" />
						</details>
					</div>
				);

			case 'mermaid':
				return (
					<div className="flex flex-col gap-2">
						<Mermaid chart={artifact.content} />
						<details className="text-xs">
							<summary className="cursor-pointer text-muted-foreground hover:text-foreground">
								View Source
							</summary>
							<CodeBlock code={artifact.content} language="mermaid" />
						</details>
					</div>
				);

			case 'markdown':
			case 'document':
				return <MessageResponse>{artifact.content}</MessageResponse>;

			case 'jsx':
			case 'chart':
				return (
					<div className="flex flex-col gap-2">
						<JSXPreview jsx={artifact.content} className="min-h-[300px]">
							<div className="absolute top-2 right-2 z-10">
								<JSXPreviewExport filename={artifact.title?.replace(/[^a-z0-9]/gi, '_') || 'chart'} />
							</div>
							<div className="pt-10">
								<JSXPreviewContent />
							</div>
						</JSXPreview>
						<details className="text-xs">
							<summary className="cursor-pointer text-muted-foreground hover:text-foreground">
								View Source
							</summary>
							<CodeBlock code={artifact.content} language="jsx" />
						</details>
					</div>
				);

			default:
				return (
					<pre className="whitespace-pre-wrap text-sm font-mono p-4 bg-muted/50 rounded">
						{artifact.content}
					</pre>
				);
		}
	};

	const Icon = ARTIFACT_ICONS[artifact.type] || CodeIcon;

	return (
		<Artifact
			className={cn(
				'my-4',
				isFullscreen && 'fixed inset-4 z-50 shadow-2xl',
				className
			)}
		>
			<ArtifactHeader>
				<div className="flex items-center gap-2 min-w-0 flex-1">
					<Icon className="size-4 shrink-0 text-muted-foreground" />
					<div className="min-w-0 flex-1">
						<ArtifactTitle className="truncate">
							{artifact.title || `${artifact.type} artifact`}
						</ArtifactTitle>
						{artifact.language && (
							<ArtifactDescription className="truncate">
								{artifact.language}
							</ArtifactDescription>
						)}
					</div>
				</div>
			<ArtifactActions>
				{messageId && (artifact.type === 'jsx' || artifact.type === 'chart') && (
					<ArtifactAction
						icon={ExternalLinkIcon}
						tooltip="Open full screen"
						label="Open in new tab"
						onClick={handleOpenPreview}
					/>
				)}
				<ArtifactAction
					icon={isCopied ? CheckIcon : CopyIcon}
					tooltip={isCopied ? 'Copied!' : 'Copy'}
					label="Copy content"
					onClick={handleCopy}
				/>
				<ArtifactAction
					icon={DownloadIcon}
					tooltip="Download"
					label="Download file"
					onClick={handleDownload}
				/>
				<ArtifactAction
					icon={isFullscreen ? MinimizeIcon : MaximizeIcon}
					tooltip={isFullscreen ? 'Exit fullscreen' : 'Fullscreen'}
					label={isFullscreen ? 'Exit fullscreen' : 'Enter fullscreen'}
					onClick={toggleFullscreen}
				/>
				{onClose && <ArtifactClose onClick={onClose} />}
			</ArtifactActions>
			</ArtifactHeader>
			<ArtifactContent className={isFullscreen ? 'flex-1' : ''}>
				{renderContent()}
			</ArtifactContent>
		</Artifact>
	);
}

export default ArtifactRenderer;
