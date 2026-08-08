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

const JSON_WRAPPER_ANSWER_KEYS = new Set(['answer', 'condensed_answer', 'response']);

/**
 * Some local models (e.g. gemma) wrap final answers in a single-key JSON
 * object (`{"answer": "..."}`), mimicking the tool-result shape. Unwrap it
 * for display only; stored content is unchanged.
 */
export function unwrapJsonWrappedAnswer(content: string): string {
	const trimmed = (content || '').trim();
	if (!trimmed.startsWith('{') || !trimmed.endsWith('}')) {
		return content;
	}
	try {
		const parsed: unknown = JSON.parse(trimmed);
		if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
			const keys = Object.keys(parsed);
			if (
				keys.length === 1 &&
				JSON_WRAPPER_ANSWER_KEYS.has(keys[0]) &&
				typeof (parsed as Record<string, unknown>)[keys[0]] === 'string'
			) {
				return (parsed as Record<string, string>)[keys[0]];
			}
		}
	} catch {
		// Not JSON — render as-is.
	}
	return content;
}

export function parseMessagePreviewContent(content: string): ParsedMessageContent {
	const decoded = unwrapJsonWrappedAnswer(decodeHtmlEntities(content || ''));

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
