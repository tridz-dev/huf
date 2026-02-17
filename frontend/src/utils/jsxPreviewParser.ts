/**
 * Parser for AI-generated JSX preview tags in message content.
 *
 * Detects and extracts JSX preview requests from AI responses using XML-style tags:
 * <jsx-preview>
 * <div>JSX content here</div>
 * </jsx-preview>
 * or
 * <jsx-preview jsx="<div>JSX content</div>" />
 */

import type {
	ParsedJSXPreview,
	JSXPreviewParseResult,
} from '@/types/artifact.types';

// Regex to match jsx-preview tags (with content or self-closing)
// Matches both <jsx-preview>content</jsx-preview> and <jsx-preview jsx="..." />
const JSX_PREVIEW_REGEX =
	/<jsx-preview\s*([^>]*?)>(?:([\s\S]*?)<\/jsx-preview>|(?:\/>))/gi;

// Regex to extract individual attributes from the tag
const ATTR_REGEX = /(\w+)=["']([^"']*)["']/g;

/**
 * Strip markdown code fences that wrap jsx-preview tags.
 * Agents sometimes output: ```xml\n<jsx-preview>...</jsx-preview>\n```
 * We need to unwrap these so the parser can find the tags.
 */
function unwrapCodeFences(content: string): string {
	// Match code fences (```xml, ```jsx, ```html, or bare ```) that contain jsx-preview tags
	return content.replace(
		/```(?:xml|jsx|html|tsx)?\s*\n?\s*(<jsx-preview[\s\S]*?<\/jsx-preview>)\s*\n?\s*```/gi,
		'$1'
	);
}

/**
 * Parse JSX preview tags from content string.
 *
 * @param content - The raw content string potentially containing JSX preview tags
 * @returns Object with remaining text and extracted JSX previews
 */
export function parseJSXPreviews(content: string): JSXPreviewParseResult {
	const previews: ParsedJSXPreview[] = [];

	// Unwrap any code fences around jsx-preview tags before parsing
	content = unwrapCodeFences(content);

	// Reset regex lastIndex to ensure we start from the beginning
	JSX_PREVIEW_REGEX.lastIndex = 0;

	const text = content.replace(JSX_PREVIEW_REGEX, (_match, attrs, body) => {
		const attributes: Record<string, string> = {};

		// Reset ATTR_REGEX for each match
		ATTR_REGEX.lastIndex = 0;
		let attrMatch;
		while ((attrMatch = ATTR_REGEX.exec(attrs)) !== null) {
			attributes[attrMatch[1]] = attrMatch[2];
		}

		// Get JSX content from either attribute or body
		const jsxContent = attributes.jsx || body || '';

		// Only add if we have valid JSX content
		if (jsxContent.trim()) {
			previews.push({
				jsx: jsxContent.trim(),
				title: attributes.title,
				isStreaming: attributes.isStreaming === 'true',
			});
		}

		// Return empty string to remove the tag from text
		return '';
	});

	// Clean up extra whitespace
	const cleanedText = text.replace(/\n{3,}/g, '\n\n').trim();

	return { text: cleanedText, previews };
}

/**
 * Check if content contains any JSX preview tags.
 *
 * @param content - The content string to check
 * @returns True if content contains at least one JSX preview tag
 */
export function hasJSXPreviews(content: string): boolean {
	if (!content) return false;
	// Unwrap code fences before checking
	content = unwrapCodeFences(content);
	// Reset regex lastIndex
	JSX_PREVIEW_REGEX.lastIndex = 0;
	return JSX_PREVIEW_REGEX.test(content);
}

/**
 * Extract just the JSX previews without modifying the text.
 *
 * @param content - The content string to extract from
 * @returns Array of parsed JSX previews
 */
export function extractJSXPreviews(content: string): ParsedJSXPreview[] {
	return parseJSXPreviews(content).previews;
}
