/**
 * Types for AI-generated artifacts and web previews
 */

export type ArtifactType =
	| 'code'
	| 'document'
	| 'html'
	| 'svg'
	| 'mermaid'
	| 'react-component'
	| 'markdown'
	| 'jsx'
	| 'chart';

export interface ParsedArtifact {
	id: string;
	type: ArtifactType;
	title?: string;
	language?: string;
	content: string;
}

export interface ParsedWebPreview {
	url: string;
	title?: string;
}

export interface ParsedJSXPreview {
	jsx: string;
	title?: string;
	isStreaming?: boolean;
}

export interface ArtifactParseResult {
	text: string;
	artifacts: ParsedArtifact[];
}

export interface WebPreviewParseResult {
	text: string;
	previews: ParsedWebPreview[];
}

export interface JSXPreviewParseResult {
	text: string;
	previews: ParsedJSXPreview[];
}
