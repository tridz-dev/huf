/**
 * Parser for AI-generated web preview tags in message content.
 *
 * Detects and extracts web preview requests from AI responses using XML-style tags:
 * <web-preview url="https://example.com" title="Example Site" />
 * or
 * <web-preview url="https://example.com" title="Example Site"></web-preview>
 */

import type {
	ParsedWebPreview,
	WebPreviewParseResult,
} from '@/types/artifact.types';

// Regex to match web-preview tags (self-closing or with closing tag)
// Matches both <web-preview url="..." /> and <web-preview url="..."></web-preview>
const WEB_PREVIEW_REGEX =
	/<web-preview\s+([^>]*?)\s*(?:\/>|><\/web-preview>)/gi;

// Regex to extract individual attributes from the tag
const ATTR_REGEX = /(\w+)=["']([^"']*)["']/g;

/**
 * Parse web preview tags from content string.
 *
 * @param content - The raw content string potentially containing web preview tags
 * @returns Object with remaining text and extracted web previews
 */
export function parseWebPreviews(content: string): WebPreviewParseResult {
	const previews: ParsedWebPreview[] = [];

	// Reset regex lastIndex to ensure we start from the beginning
	WEB_PREVIEW_REGEX.lastIndex = 0;

	const text = content.replace(WEB_PREVIEW_REGEX, (_match, attrs) => {
		const attributes: Record<string, string> = {};

		// Reset ATTR_REGEX for each match
		ATTR_REGEX.lastIndex = 0;
		let attrMatch;
		while ((attrMatch = ATTR_REGEX.exec(attrs)) !== null) {
			attributes[attrMatch[1]] = attrMatch[2];
		}

		// Only add if we have a valid URL
		if (attributes.url) {
			previews.push({
				url: attributes.url,
				title: attributes.title,
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
 * Check if content contains any web preview tags.
 *
 * @param content - The content string to check
 * @returns True if content contains at least one web preview tag
 */
export function hasWebPreviews(content: string): boolean {
	if (!content) return false;
	// Reset regex lastIndex
	WEB_PREVIEW_REGEX.lastIndex = 0;
	return WEB_PREVIEW_REGEX.test(content);
}

/**
 * Extract just the web previews without modifying the text.
 *
 * @param content - The content string to extract from
 * @returns Array of parsed web previews
 */
export function extractWebPreviews(content: string): ParsedWebPreview[] {
	return parseWebPreviews(content).previews;
}

/**
 * Validate a URL string for use in web preview.
 *
 * @param url - The URL string to validate
 * @returns True if the URL is valid and safe for iframe embedding
 */
export function isValidPreviewUrl(url: string): boolean {
	try {
		const parsed = new URL(url);
		// Only allow http and https protocols
		return parsed.protocol === 'http:' || parsed.protocol === 'https:';
	} catch {
		return false;
	}
}
