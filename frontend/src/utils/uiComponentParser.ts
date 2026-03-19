/**
 * Parser for AI-generated structured UI component tags in message content.
 *
 * Detects and extracts <ui-component> tags that carry a type and JSON data payload.
 * Each tag is self-closing and looks like:
 *   <ui-component type="stats-card" data='{"title":"Revenue","value":48250}' />
 *
 * The data attribute uses single-quoted JSON so double quotes inside the JSON
 * don't break the attribute boundary.  HTML-encoded entities (&quot; &amp;) are
 * decoded before JSON.parse.
 */

import type {
	ParsedUIComponent,
	UIComponentParseResult,
} from '@/types/artifact.types';

// Matches self-closing <ui-component type="..." data='...' /> tags.
// Capture group 1 = type value, group 2 = data value (single- or double-quoted).
const UI_COMPONENT_REGEX =
	/<ui-component\s+type=["']([^"']+)["']\s+data='((?:[^'\\]|\\.)*)'\s*\/>/gi;

// Fallback for data wrapped in double quotes (less common because JSON uses double quotes internally)
const UI_COMPONENT_REGEX_DQ =
	/<ui-component\s+type=["']([^"']+)["']\s+data="((?:[^"\\]|\\.)*)"\s*\/>/gi;

function decodeDataValue(raw: string): string {
	return raw
		.replace(/&quot;/g, '"')
		.replace(/&amp;/g, '&')
		.replace(/&lt;/g, '<')
		.replace(/&gt;/g, '>')
		.replace(/&#39;/g, "'");
}

function extractComponents(
	content: string,
	regex: RegExp,
): { text: string; components: ParsedUIComponent[] } {
	const components: ParsedUIComponent[] = [];
	regex.lastIndex = 0;

	const text = content.replace(regex, (_match, type: string, rawData: string) => {
		try {
			const decoded = decodeDataValue(rawData);
			const data = JSON.parse(decoded) as Record<string, unknown>;
			components.push({ type, data });
		} catch {
			components.push({ type, data: null, error: 'Invalid JSON in data attribute' });
		}
		return '';
	});

	return { text, components };
}

/**
 * Parse <ui-component> tags from message content.
 */
export function parseUIComponents(content: string): UIComponentParseResult {
	// Try single-quoted data first (preferred), then double-quoted fallback
	let result = extractComponents(content, UI_COMPONENT_REGEX);
	if (result.components.length === 0) {
		result = extractComponents(content, UI_COMPONENT_REGEX_DQ);
	}

	const cleanedText = result.text.replace(/\n{3,}/g, '\n\n').trim();
	return { text: cleanedText, components: result.components };
}

/**
 * Quick check for presence of <ui-component> tags.
 */
export function hasUIComponents(content: string): boolean {
	if (!content) return false;
	UI_COMPONENT_REGEX.lastIndex = 0;
	UI_COMPONENT_REGEX_DQ.lastIndex = 0;
	return UI_COMPONENT_REGEX.test(content) || UI_COMPONENT_REGEX_DQ.test(content);
}
