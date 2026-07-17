/**
 * Shared message content parsing for chat and preview views.
 * Parse order: JSX previews → web previews → artifacts.
 */

import { parseArtifacts, hasArtifacts } from '@/utils/artifactParser';
import { parseWebPreviews, hasWebPreviews } from '@/utils/webPreviewParser';
import { parseJSXPreviews, hasJSXPreviews } from '@/utils/jsxPreviewParser';
import { decodeHtmlEntities } from '@/utils/decodeHtmlEntities';
import type { ParsedArtifact, ParsedWebPreview, ParsedJSXPreview } from '@/types/artifact.types';

export interface ParsedMessageContent {
	textContent: string;
	jsxPreviews: ParsedJSXPreview[];
	webPreviews: ParsedWebPreview[];
	artifacts: ParsedArtifact[];
}

export function parseMessagePreviewContent(content: string): ParsedMessageContent {
	const decoded = decodeHtmlEntities(content || '');

	let remaining = decoded;
	const jsxPreviews: ParsedJSXPreview[] = [];
	const webPreviews: ParsedWebPreview[] = [];
	const artifacts: ParsedArtifact[] = [];

	if (hasJSXPreviews(remaining)) {
		const parsed = parseJSXPreviews(remaining);
		remaining = parsed.text;
		jsxPreviews.push(...parsed.previews);
	}

	if (hasWebPreviews(remaining)) {
		const parsed = parseWebPreviews(remaining);
		remaining = parsed.text;
		webPreviews.push(...parsed.previews);
	}

	if (hasArtifacts(remaining)) {
		const parsed = parseArtifacts(remaining);
		remaining = parsed.text;
		artifacts.push(...parsed.artifacts);
	}

	return {
		textContent: remaining.replace(/\n{3,}/g, '\n\n').trim(),
		jsxPreviews,
		webPreviews,
		artifacts,
	};
}

export function hasJsxOrChartContent(parsed: ParsedMessageContent): boolean {
	const jsxOnlyArtifacts = parsed.artifacts.filter(
		(a) => a.type === 'jsx' || a.type === 'chart'
	);
	return parsed.jsxPreviews.length > 0 || jsxOnlyArtifacts.length > 0;
}
